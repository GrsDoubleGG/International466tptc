from __future__ import annotations

import math
from dataclasses import dataclass

G = 9.81

SUPERFICIES = {
    "Asfalto seco": (0.70, 0.007),
    "Terracería": (0.50, 0.020),
    "Terracería mojada / lodo": (0.30, 0.050),
}


@dataclass
class ParamDiferencial:
    nombre: str = "Eaton 16244 (2 velocidades, abierto)"
    relacion_alta: float = 4.88  # Dana HX500-QR, kit 096798 (16244: 4.88 / 6.55)
    relacion_baja: float = 6.55
    eficiencia_alta: float = 0.96
    eficiencia_baja: float = 0.94
    radio_rueda: float = 0.52
    inercia_ruedas: float = 48.0
    rigidez_llanta: float = 200000.0
    v_suavizado: float = 0.1


@dataclass
class CargaFija:
    masa: float = 15000.0
    pendiente: float = 0.0
    mu: float = 0.70
    crr: float = 0.007
    fraccion_eje_motriz: float = 0.65
    cda: float = 6.0
    densidad_aire: float = 1.05
    tolerancia_aceleracion: float = 0.05


@dataclass
class Balance:
    f_entregada: float
    f_requerida: float
    f_rodadura: float
    f_pendiente: float
    f_aire: float
    f_maxima: float
    f_adherencia: float
    uso_entregada: float
    uso_maxima: float
    demanda: str
    patina: bool
    velocidad: float
    aceleracion: float


class Diferencial:
    def __init__(self, param: ParamDiferencial | None = None,
                 carga: CargaFija | None = None):
        self.p = param or ParamDiferencial()
        self.carga = carga or CargaFija()
        self.rango = "alta"
        self.reiniciar()

    def reiniciar(self) -> None:
        self.w_rueda = 0.0
        self.v = 0.0
        self.a = 0.0
        self.t_eje = 0.0
        self.f_llanta = 0.0
        self.f_res = (0.0, 0.0, 0.0)
        self.patina = False

    def fijar_rango(self, rango: str) -> None:
        if rango not in ("alta", "baja"):
            raise ValueError(f"Rango desconocido: {rango}")
        self.rango = rango

    def fijar_carga(self, carga: CargaFija) -> None:
        self.carga = carga

    @property
    def relacion(self) -> float:
        return self.p.relacion_alta if self.rango == "alta" else self.p.relacion_baja

    def eficiencia(self) -> float:
        return self.p.eficiencia_alta if self.rango == "alta" else self.p.eficiencia_baja

    def velocidad_cardan(self) -> float:
        return self.w_rueda * self.relacion

    def torque_eje(self, t_cardan: float) -> float:
        eta = self.eficiencia()
        factor = eta if t_cardan >= 0.0 else 1.0 / eta
        return t_cardan * self.relacion * factor

    def fuerza_rueda(self, t_cardan: float) -> float:
        return self.torque_eje(t_cardan) / self.p.radio_rueda

    def _angulo(self) -> float:
        return math.atan(self.carga.pendiente / 100.0)

    def resistencias(self, v: float) -> tuple[float, float, float]:
        c = self.carga
        th = self._angulo()
        f_rod = c.crr * c.masa * G * math.cos(th) * math.tanh(v / self.p.v_suavizado)
        f_pend = c.masa * G * math.sin(th)
        f_aire = 0.5 * c.densidad_aire * c.cda * v * abs(v)
        return f_rod, f_pend, f_aire

    def fuerza_adherencia(self) -> float:
        c = self.carga
        return c.mu * c.masa * G * math.cos(self._angulo()) * c.fraccion_eje_motriz

    def inercia_vista_en_cardan(self) -> float:
        return self.p.inercia_ruedas / self.relacion ** 2

    def torque_reaccion_cardan(self) -> float:
        return self.f_llanta * self.p.radio_rueda / self.relacion

    def paso(self, dt: float, t_cardan: float, j_cardan: float,
             anti_retroceso: bool = True) -> None:
        r, m, c = self.p.radio_rueda, self.carga.masa, self.p.rigidez_llanta
        j = self.p.inercia_ruedas + j_cardan * self.relacion ** 2
        self.t_eje = self.torque_eje(t_cardan)
        self.f_res = self.resistencias(self.v)

        w_pred = self.w_rueda + dt * self.t_eje / j
        v_pred = self.v - dt * sum(self.f_res) / m
        s = (w_pred * r - v_pred) / (1.0 + dt * c * (r * r / j + 1.0 / m))
        f_adh = self.fuerza_adherencia()
        self.patina = abs(c * s) > f_adh
        self.f_llanta = min(max(c * s, -f_adh), f_adh)

        w_nuevo = w_pred - dt * self.f_llanta * r / j
        v_nuevo = v_pred + dt * self.f_llanta / m
        if anti_retroceso and v_nuevo < 0.0:
            v_nuevo = 0.0
            w_nuevo = max(w_nuevo, 0.0)
        self.a = (v_nuevo - self.v) / dt
        self.w_rueda, self.v = w_nuevo, v_nuevo

    def balance(self, f_maxima: float) -> Balance:
        f_ent = self.t_eje / self.p.radio_rueda
        f_rod, f_pend, f_aire = self.f_res
        f_req = f_rod + f_pend + f_aire
        tol = self.carga.masa * self.carga.tolerancia_aceleracion
        if self.patina:
            demanda = "patina"
        elif f_req > f_ent + tol:
            demanda = "mas"
        elif f_ent > f_req + tol:
            demanda = "menos"
        else:
            demanda = "suficiente"
        return Balance(
            f_entregada=f_ent,
            f_requerida=f_req,
            f_rodadura=f_rod,
            f_pendiente=f_pend,
            f_aire=f_aire,
            f_maxima=f_maxima,
            f_adherencia=self.fuerza_adherencia(),
            uso_entregada=f_req / f_ent if f_ent > 1.0 else math.inf,
            uso_maxima=f_req / f_maxima if f_maxima > 1.0 else math.inf,
            demanda=demanda,
            patina=self.patina,
            velocidad=self.v,
            aceleracion=self.a,
        )

    @staticmethod
    def evaluar(b: Balance) -> tuple[str, str]:
        if b.demanda == "patina":
            return "overload", "Patina: el piso no sostiene la fuerza"
        if b.demanda == "mas":
            return "overload", "Requiere más fuerza: pierde velocidad"
        if b.demanda == "menos":
            return "underload", "Sobra fuerza: gana velocidad"
        return "stable", "Fuerza justa para la carga"