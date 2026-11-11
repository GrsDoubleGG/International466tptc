from __future__ import annotations

from dataclasses import dataclass, field

RAD_A_RPM = 9.549296585513721

RELACIONES_RT8908LL = {
    "N": 0.0,
    "LL": 19.58,
    "L": 12.67,
    "1": 8.39,
    "2": 6.23,
    "3": 4.58,
    "4": 3.40,
    "5": 2.46,
    "6": 1.83,
    "7": 1.35,  # manual RT-8908LL, p. 00-02
    "8": 1.00,
}


@dataclass
class ParamEmbrague:
    rpm_inicio: float = 1000.0
    rpm_pleno: float = 1400.0
    rpm_suelta: float = 750.0
    desliz_acople: float = 3.0
    torque_max: float = 1400.0
    rigidez: float = 600.0
    patina_tolerada: float = 2.0


class Embrague:
    def __init__(self, param: ParamEmbrague | None = None):
        self.p = param or ParamEmbrague()
        self.reiniciar()

    def reiniciar(self) -> None:
        self.torque = 0.0
        self.deslizamiento = 0.0
        self.acoplado = False
        self.t_patinando = 0.0

    def soltar(self) -> None:
        self.acoplado = False

    def capacidad(self, rpm_motor: float) -> float:
        p = self.p
        if self.acoplado:
            return p.torque_max
        acople = (rpm_motor - p.rpm_inicio) / (p.rpm_pleno - p.rpm_inicio)
        return p.torque_max * min(max(acople, 0.0), 1.0)

    def condicion(self) -> str:
        if self.acoplado:
            return "acoplado"
        return "patinando" if self.torque != 0.0 else "abierto"

    def acoplar(self, dt: float, w_motor: float, w_entrada: float,
                j_motor: float, j_entrada: float,
                t_motor: float, t_entrada: float) -> float:
        p = self.p
        rpm = w_motor * RAD_A_RPM
        self.deslizamiento = w_motor - w_entrada
        if self.acoplado and rpm < p.rpm_suelta:
            self.acoplado = False
        cap = self.capacidad(rpm)
        if cap <= 0.0:
            self.torque = 0.0
            self.t_patinando = 0.0
            return 0.0
        k = p.rigidez
        w_m = w_motor + dt * t_motor / j_motor
        w_e = w_entrada + dt * t_entrada / j_entrada
        s = (w_m - w_e) / (1.0 + dt * k * (1.0 / j_motor + 1.0 / j_entrada))
        self.torque = min(max(k * s, -cap), cap)
        if not self.acoplado and abs(self.deslizamiento) < p.desliz_acople:
            self.acoplado = True
        self.t_patinando = 0.0 if self.acoplado else self.t_patinando + dt
        return self.torque

    def quemandose(self) -> bool:
        return self.t_patinando > self.p.patina_tolerada


@dataclass
class ParamTransmision:
    nombre: str = "Eaton Fuller RT-8908LL"
    relaciones: dict = field(default_factory=lambda: dict(RELACIONES_RT8908LL))
    eficiencia_directa: float = 0.99
    eficiencia_indirecta: float = 0.97
    torque_max_entrada: float = 1166.0
    inercia_entrada: float = 0.06
    rpm_banda_min: float = 1150.0
    rpm_banda_max: float = 2300.0
    uso_minimo: float = 0.05
    uso_maximo: float = 0.95
    combustible_tope: float = 0.95
    combustible_holgado: float = 0.5


@dataclass
class EstadoTransmision:
    marcha: str
    relacion: float
    eficiencia: float
    torque_entrada: float
    torque_salida: float
    rpm_entrada: float
    rpm_salida: float
    uso_capacidad: float
    deslizamiento_rpm: float
    embrague: str


class Transmision:
    def __init__(self, param: ParamTransmision | None = None,
                 embrague: Embrague | None = None):
        self.p = param or ParamTransmision()
        self.embrague = embrague or Embrague()
        self.marcha = "1"

    def reiniciar(self) -> None:
        self.embrague.reiniciar()

    def marchas(self) -> list[str]:
        return list(self.p.relaciones.keys())

    def seleccionar(self, marcha: str) -> None:
        if marcha not in self.p.relaciones:
            raise ValueError(f"Marcha desconocida: {marcha}")
        if marcha != self.marcha:
            self.embrague.soltar()
        self.marcha = marcha

    @property
    def relacion(self) -> float:
        return self.p.relaciones[self.marcha]

    @property
    def en_neutral(self) -> bool:
        return self.relacion == 0.0

    def eficiencia(self) -> float:
        return self.p.eficiencia_directa if self.relacion == 1.0 else self.p.eficiencia_indirecta

    def torque_salida(self, t_entrada: float) -> float:
        if self.en_neutral:
            return 0.0
        eta = self.eficiencia()
        factor = eta if t_entrada >= 0.0 else 1.0 / eta
        return t_entrada * self.relacion * factor

    def velocidad_entrada(self, w_salida: float) -> float:
        return w_salida * self.relacion

    def torque_reflejado_entrada(self, t_salida: float) -> float:
        return 0.0 if self.en_neutral else t_salida / self.relacion

    def inercia_reflejada_salida(self) -> float:
        return self.p.inercia_entrada * self.relacion ** 2

    def inercia_vista_en_entrada(self, j_salida: float) -> float:
        if self.en_neutral:
            return self.p.inercia_entrada
        return self.p.inercia_entrada + j_salida / self.relacion ** 2

    def estado(self, w_salida: float) -> EstadoTransmision:
        t_in = self.embrague.torque
        return EstadoTransmision(
            marcha=self.marcha,
            relacion=self.relacion,
            eficiencia=self.eficiencia(),
            torque_entrada=t_in,
            torque_salida=self.torque_salida(t_in),
            rpm_entrada=self.velocidad_entrada(w_salida) * RAD_A_RPM,
            rpm_salida=w_salida * RAD_A_RPM,
            uso_capacidad=abs(t_in) / self.p.torque_max_entrada,
            deslizamiento_rpm=self.embrague.deslizamiento * RAD_A_RPM,
            embrague=self.embrague.condicion(),
        )

    def evaluar(self, rpm_motor: float, combustible: float) -> tuple[str, str]:
        p = self.p
        if self.en_neutral:
            return "underload", "En neutral"
        uso = abs(self.embrague.torque) / p.torque_max_entrada
        if uso > p.uso_maximo:
            return "overload", "Torque de entrada sobre la capacidad"
        if self.embrague.quemandose():
            return "overload", "Embrague patinando: marcha larga"
        if rpm_motor < p.rpm_banda_min and combustible >= p.combustible_tope:
            return "overload", "Marcha larga: falta multiplicación"
        if uso < p.uso_minimo:
            return "underload", "Casi sin torque transmitido"
        if rpm_motor > p.rpm_banda_max and combustible < p.combustible_holgado:
            return "underload", "Marcha corta: admite subir"
        return "stable", "Multiplicación adecuada"