from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass

RAD_A_RPM = 60.0 / (2.0 * math.pi)
RPM_A_RAD = 1.0 / RAD_A_RPM


@dataclass
class ParamMotor:
    nombre: str = "International DT466E 225 HP (EPA 98)"
    # Curva a plena carga digitalizada de la gráfica "DT466E 225 EPA 98"
    # (folleto International "DT 466 engine specifications and benefits").
    # Leída en lb-ft: 800:400, 1000:500, 1200:573, 1450:627, 1800:636, 2050:628, 2400:500, 2700:452, 2810:300, 2835:0
    # Convertida a N·m (x 1.3558). Ojo: en esa gráfica el eje de rpm salta 800->1000
    # en la primera división; aquí se toma tal como está rotulado.
    curva_rpm: tuple = (800, 1000, 1200, 1450, 1800, 2050, 2400, 2700, 2810, 2835)
    curva_torque: tuple = (542, 678, 777, 850, 862, 851, 678, 613, 407, 0)
    rpm_ralenti: float = 700.0
    rpm_gobernada: float = 2600.0
    rpm_ahogo: float = 350.0
    rpm_sobregiro: float = 2900.0
    inercia: float = 2.5
    friccion_base: float = 35.0
    friccion_rpm: float = 0.025
    kp: float = 0.006
    ki: float = 0.004
    limite_integral: float = 0.3
    umbral_bajo: float = 0.25
    umbral_saturado: float = 0.97
    margen_rpm: float = 150.0
    subida_minima: float = 10.0
    filtro_tasa: float = 0.05


@dataclass
class EstadoMotor:
    rpm: float
    rpm_objetivo: float
    combustible: float
    torque_neto: float
    torque_maximo: float
    torque_carga: float
    potencia_kw: float
    rpm_por_s: float
    apagado: bool


class Motor:
    def __init__(self, param: ParamMotor | None = None):
        self.p = param or ParamMotor()
        self.reiniciar()

    def reiniciar(self) -> None:
        self.omega = self.p.rpm_ralenti * RPM_A_RAD
        self.acelerador = 0.0
        self.integral = 0.0
        self.torque_carga = 0.0
        self.rpm_por_s = 0.0
        self.apagado = False
        self.combustible = 0.0
        self._gobernar(0.0)

    @property
    def rpm(self) -> float:
        return self.omega * RAD_A_RPM

    def fijar_acelerador(self, fraccion: float) -> None:
        self.acelerador = min(max(fraccion, 0.0), 1.0)

    def rpm_objetivo(self) -> float:
        p = self.p
        return p.rpm_ralenti + self.acelerador * (p.rpm_gobernada - p.rpm_ralenti)

    def torque_curva(self, rpm: float) -> float:
        xs, ys = self.p.curva_rpm, self.p.curva_torque
        if rpm <= xs[0]:
            escala = (rpm - self.p.rpm_ahogo) / (xs[0] - self.p.rpm_ahogo)
            return ys[0] * min(max(escala, 0.0), 1.0)
        if rpm >= xs[-1]:
            return ys[-1]
        k = bisect_right(xs, rpm)
        x0, x1, y0, y1 = xs[k - 1], xs[k], ys[k - 1], ys[k]
        return y0 + (y1 - y0) * (rpm - x0) / (x1 - x0)

    def torque_friccion(self, rpm: float) -> float:
        if rpm <= 0.0:
            return 0.0
        return self.p.friccion_base + self.p.friccion_rpm * rpm

    def torque_maximo(self) -> float:
        return 0.0 if self.apagado else self.torque_curva(self.rpm)

    def torque_neto(self) -> float:
        rpm = self.rpm
        t_fric = self.torque_friccion(rpm)
        if self.apagado:
            return -t_fric
        return self.combustible * (self.torque_curva(rpm) + t_fric) - t_fric

    def paso(self, dt: float, torque_carga: float) -> None:
        self.torque_carga = torque_carga
        alfa = (self.torque_neto() - torque_carga) / self.p.inercia
        self.omega = max(self.omega + dt * alfa, 0.0)
        tasa = alfa * RAD_A_RPM
        k = min(dt / self.p.filtro_tasa, 1.0)
        self.rpm_por_s += k * (tasa - self.rpm_por_s)
        if not self.apagado and self.rpm < self.p.rpm_ahogo:
            self.apagado = True
            self.combustible = 0.0
        if not self.apagado:
            self._gobernar(dt)

    def _gobernar(self, dt: float) -> None:
        rpm = self.rpm
        t_fric = self.torque_friccion(rpm)
        capacidad = self.torque_curva(rpm) + t_fric
        if capacidad <= 0.0:
            self.combustible = 0.0
            return
        error = self.rpm_objetivo() - rpm
        anticipacion = (self.torque_carga + t_fric) / capacidad
        pedido = anticipacion + self.p.kp * error + self.integral
        saturado = (pedido >= 1.0 and error > 0.0) or (pedido <= 0.0 and error < 0.0)
        if not saturado:
            lim = self.p.limite_integral
            self.integral = min(max(self.integral + self.p.ki * error * dt, -lim), lim)
        self.combustible = min(max(pedido, 0.0), 1.0)

    def estado(self) -> EstadoMotor:
        t_neto = self.torque_neto()
        return EstadoMotor(
            rpm=self.rpm,
            rpm_objetivo=self.rpm_objetivo(),
            combustible=self.combustible,
            torque_neto=t_neto,
            torque_maximo=self.torque_maximo(),
            torque_carga=self.torque_carga,
            potencia_kw=t_neto * self.omega / 1000.0,
            rpm_por_s=self.rpm_por_s,
            apagado=self.apagado,
        )

    def evaluar(self) -> tuple[str, str]:
        p = self.p
        rpm = self.rpm
        if self.apagado:
            return "overload", "Motor ahogado"
        if rpm > p.rpm_sobregiro:
            return "overload", "Sobregiro: la carga arrastra al motor"
        a_tope = self.combustible >= p.umbral_saturado
        if a_tope and rpm < self.rpm_objetivo() - p.margen_rpm:
            if self.rpm_por_s < p.subida_minima:
                return "overload", "A tope y no alcanza las rpm pedidas"
            return "stable", "A plena carga, ganando rpm"
        if self.combustible < p.umbral_bajo:
            return "underload", "Carga ligera"
        return "stable", "Sostiene las rpm pedidas"