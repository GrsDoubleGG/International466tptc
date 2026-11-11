"""
Chofer de Springfield: la misma interfaz de Chofer.py, pero el modelo corre en C
(springfield.c). Python solo dibuja; todas las cuentas las hace el ejecutable.

Primero compila el modelo en la misma carpeta que este archivo:
    Windows (Developer Command Prompt for VS):  cl /O2 /utf-8 springfield.c
    Linux / MinGW:                              gcc -O2 -o springfield springfield.c -lm

Luego:
    python chofer_springfield.py               interfaz gráfica
    python chofer_springfield.py --prueba      los tres episodios en consola
    python chofer_springfield.py --exe RUTA    si el ejecutable está en otro lado
"""
from __future__ import annotations

import argparse
import math
import subprocess
import sys
import time
import tkinter as tk
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import ttk, messagebox

COMPONENTES = ("motor", "transmision", "diferencial")
ESTADOS = ("underload", "stable", "overload")
MARCHAS = ("N", "LL", "L", "1", "2", "3", "4", "5", "6", "7", "8")   # mismo orden que el enum en C
CONDICION_EMBRAGUE = ("abierto", "patinando", "acoplado")

SUPERFICIES = {
    "Asfalto seco": (0.70, 0.007),
    "Terracería": (0.50, 0.020),
    "Terracería mojada / lodo": (0.30, 0.050),
}

INSTRUCCIONES_COMPILAR = (
    "No encontré el ejecutable de springfield.c junto a este archivo.\n\n"
    "Compílalo en la misma carpeta:\n"
    "  Windows:  cl /O2 /utf-8 springfield.c\n"
    "  gcc:      gcc -O2 -o springfield springfield.c -lm\n\n"
    "o indica la ruta con --exe."
)


# ================================================================ datos que manda el C

@dataclass
class Configuracion:
    marcha: str = "1"
    rango: str = "alta"
    masa: float = 15000.0
    pendiente: float = 0.0
    superficie: str = "Asfalto seco"


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


@dataclass
class EstadoTransmision:
    marcha: str
    relacion: float
    eficiencia: float
    torque_entrada: float
    torque_salida: float
    rpm_salida: float
    uso_capacidad: float
    deslizamiento_rpm: float
    embrague: str


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
    velocidad: float
    aceleracion: float


@dataclass
class Lectura:
    t: float
    acelerador: float
    motor: EstadoMotor
    trans: EstadoTransmision
    balance: Balance
    relacion_diff: float
    torque_eje: float
    estados: dict = field(default_factory=dict)


def _parsear(linea: str) -> Lectura:
    partes = linea.rstrip("\r\n").split("|")
    if len(partes) != 4:
        raise RuntimeError(f"Respuesta rara del C: {linea!r}")
    v = [float(x) for x in partes[0].split()]
    if len(v) != 34:
        raise RuntimeError(f"Esperaba 34 números y llegaron {len(v)}")
    f_ent, f_req, f_max = v[22], v[23], v[27]
    return Lectura(
        t=v[0],
        acelerador=v[1],
        motor=EstadoMotor(
            rpm=v[2], rpm_objetivo=v[3], combustible=v[4], torque_neto=v[5],
            torque_maximo=v[6], torque_carga=v[7], potencia_kw=v[8], rpm_por_s=v[9],
            apagado=bool(v[10]),
        ),
        trans=EstadoTransmision(
            marcha=MARCHAS[int(v[11])], relacion=v[12], eficiencia=v[13],
            torque_entrada=v[14], torque_salida=v[15], rpm_salida=v[16],
            uso_capacidad=v[17], deslizamiento_rpm=v[18],
            embrague=CONDICION_EMBRAGUE[int(v[19])],
        ),
        balance=Balance(
            f_entregada=f_ent, f_requerida=f_req, f_rodadura=v[24], f_pendiente=v[25],
            f_aire=v[26], f_maxima=f_max, f_adherencia=v[28],
            uso_entregada=f_req / f_ent if f_ent > 1.0 else math.inf,
            uso_maxima=f_req / f_max if f_max > 1.0 else math.inf,
            velocidad=v[29], aceleracion=v[30],
        ),
        relacion_diff=v[20],
        torque_eje=v[21],
        estados={
            "motor": (ESTADOS[int(v[31])], partes[1]),
            "transmision": (ESTADOS[int(v[32])], partes[2]),
            "diferencial": (ESTADOS[int(v[33])], partes[3]),
        },
    )


# ================================================================ puente con el ejecutable

def encontrar_exe(ruta: str | None) -> str | None:
    if ruta:
        return ruta if Path(ruta).exists() else None
    aqui = Path(__file__).resolve().parent
    for nombre in ("springfield.exe", "springfield"):
        p = aqui / nombre
        if p.exists():
            return str(p)
    return None


class TrenMotrizC:
    """Mismo papel que TrenMotriz en Chofer.py, pero cada paso lo calcula el C."""

    def __init__(self, exe: str):
        self.proc = subprocess.Popen(
            [exe, "--chofer"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.acelerador = 0.0
        self._ultima = self._pedir("lee")

    @property
    def t(self) -> float:
        return self._ultima.t

    def _pedir(self, orden: str) -> Lectura:
        try:
            self.proc.stdin.write(orden + "\n")
            self.proc.stdin.flush()
            linea = self.proc.stdout.readline()
        except (BrokenPipeError, OSError) as e:
            raise RuntimeError("El modelo en C dejó de responder") from e
        if not linea:
            raise RuntimeError("El modelo en C se cerró (¿se compiló bien?)")
        self._ultima = _parsear(linea)
        return self._ultima

    def configurar(self, cfg: Configuracion) -> None:
        mu, crr = SUPERFICIES[cfg.superficie]
        marcha = MARCHAS.index(cfg.marcha)
        alto = 1 if cfg.rango == "alta" else 0
        self._pedir(f"config {marcha} {alto} {cfg.masa!r} {cfg.pendiente!r} {mu!r} {crr!r}")

    def reiniciar(self) -> None:
        self._pedir("reinicia")

    def fijar_acelerador(self, fraccion: float) -> None:
        self.acelerador = min(max(fraccion, 0.0), 1.0)
        self._pedir(f"pedal {self.acelerador!r}")

    def avanzar(self, duracion: float) -> None:
        self._pedir(f"avanza {duracion!r}")

    def lectura(self) -> Lectura:
        return self._pedir("lee")

    def cerrar(self) -> None:
        if self.proc.poll() is None:
            try:
                self.proc.stdin.write("adios\n")
                self.proc.stdin.flush()
                self.proc.wait(timeout=1.0)
            except Exception:
                self.proc.kill()


class Indicador:
    def __init__(self, retardo: float = 0.4):
        self.retardo = retardo
        self.reiniciar()

    def reiniciar(self) -> None:
        self.estado, self.mensaje = "stable", ""
        self._candidato, self._t = None, 0.0

    def actualizar(self, estado: str, mensaje: str, dt: float) -> None:
        if estado == self.estado:
            self.mensaje, self._candidato = mensaje, None
            return
        if estado != self._candidato:
            self._candidato, self._t = estado, 0.0
        self._t += dt
        if self._t >= self.retardo:
            self.estado, self.mensaje, self._candidato = estado, mensaje, None


# ================================================================ interfaz gráfica

COLORES = {
    "underload": "#2f7fc1",
    "stable": "#2e9e5b",
    "overload": "#d64541",
    "apagado": "#d4d4d4",
    "fondo": "#f4f4f2",
    "tinta": "#1f1f1f",
    "tenue": "#6b6b6b",
    "flecha": "#9a9a9a",
    "rpm": "#b0541f",
    "vel": "#2f5fa8",
}
TINTES = {"underload": "#dbe9f6", "stable": "#dcf0e3", "overload": "#f8dcdb"}
ETIQUETAS = {"underload": "UNDER", "stable": "STABLE", "overload": "OVER"}
FUENTE = "Segoe UI"

SUBTITULOS = (
    "Planta Nuclear de Springfield\nDT466E · 862 N·m @ 1800 rpm",
    "Kwik-E-Mart de Apu\nRT-8908LL · 8 + 2 bajas, 1166 N·m",
    "Patty y Selma\nEaton 16244 · 4.88 / 6.55",
)


class Diagrama(tk.Canvas):
    ANCHO, ALTO = 860, 280
    CAJA_W, CAJA_H, CAJA_Y = 220, 104, 24
    XS = (16, 312, 608)
    TITULOS = ("MOTOR", "TRANSMISIÓN", "DIFERENCIAL")

    def __init__(self, padre, subtitulos):
        super().__init__(padre, width=self.ANCHO, height=self.ALTO,
                         bg=COLORES["fondo"], highlightthickness=0)
        self.cajas, self.lamparas, self.mensajes, self.ejes = {}, {}, {}, []
        self._dibujar_ejes()
        for nombre, x, titulo, sub in zip(COMPONENTES, self.XS, self.TITULOS, subtitulos):
            self._dibujar_componente(nombre, x, titulo, sub)

    def _dibujar_ejes(self):
        y = self.CAJA_Y + self.CAJA_H / 2
        tramos = [(self.XS[0] + self.CAJA_W, self.XS[1]), (self.XS[1] + self.CAJA_W, self.XS[2])]
        for x0, x1 in tramos:
            self.create_line(x0, y, x1, y, width=6, fill=COLORES["flecha"], arrow="last")
            self.ejes.append(self.create_text((x0 + x1) / 2, y - 14, text="",
                                              font=(FUENTE, 9, "bold"), fill=COLORES["tinta"]))
        x_fin = self.XS[2] + self.CAJA_W
        self.create_line(x_fin, y, x_fin + 26, y, width=6, fill=COLORES["flecha"], arrow="last")
        self.ejes.append(self.create_text(self.XS[2] + self.CAJA_W / 2, self.CAJA_Y - 12, text="",
                                          font=(FUENTE, 9, "bold"), fill=COLORES["tinta"]))

    def _dibujar_componente(self, nombre, x, titulo, sub):
        y = self.CAJA_Y
        self.cajas[nombre] = self.create_rectangle(
            x, y, x + self.CAJA_W, y + self.CAJA_H, width=3,
            outline=COLORES["stable"], fill=TINTES["stable"])
        self.create_text(x + self.CAJA_W / 2, y + 32, text=titulo,
                         font=(FUENTE, 15, "bold"), fill=COLORES["tinta"])
        self.create_text(x + self.CAJA_W / 2, y + 72, text=sub, width=self.CAJA_W - 16,
                         font=(FUENTE, 9), fill=COLORES["tenue"], justify="center")
        lamparas = {}
        for j, est in enumerate(ESTADOS):
            cx, cy = x + 37 + j * 73, y + self.CAJA_H + 30
            lamparas[est] = self.create_oval(cx - 14, cy - 14, cx + 14, cy + 14,
                                             fill=COLORES["apagado"], outline=COLORES["flecha"])
            self.create_text(cx, cy + 26, text=ETIQUETAS[est],
                             font=(FUENTE, 8, "bold"), fill=COLORES["tenue"])
        self.lamparas[nombre] = lamparas
        self.mensajes[nombre] = self.create_text(
            x + self.CAJA_W / 2, y + self.CAJA_H + 76, text="", width=self.CAJA_W,
            font=(FUENTE, 10), fill=COLORES["tinta"], justify="center", anchor="n")

    def pintar(self, indicadores, lec: Lectura):
        for nombre in COMPONENTES:
            est = indicadores[nombre].estado
            self.itemconfigure(self.cajas[nombre], outline=COLORES[est], fill=TINTES[est])
            for e, oval in self.lamparas[nombre].items():
                self.itemconfigure(oval, fill=COLORES[e] if e == est else COLORES["apagado"])
            self.itemconfigure(self.mensajes[nombre], text=indicadores[nombre].mensaje)
        self.itemconfigure(self.ejes[0], text=f"{lec.trans.torque_entrada:,.0f} N·m")
        self.itemconfigure(self.ejes[1], text=f"{lec.trans.torque_salida:,.0f} N·m")
        self.itemconfigure(self.ejes[2], text=f"eje {lec.torque_eje / 1000:,.1f} kN·m  →  "
                                               f"{lec.balance.f_entregada / 1000:,.1f} kN")


class Tendencia(tk.Canvas):
    ANCHO, ALTO, VENTANA = 860, 150, 40.0
    IZQ, DER, ARR, ABA = 50, 50, 14, 24
    TOPE_RPM, TOPE_KMH = 3000.0, 100.0

    def __init__(self, padre):
        super().__init__(padre, width=self.ANCHO, height=self.ALTO, bg="white",
                         highlightthickness=1, highlightbackground="#c8c8c8")
        self.datos = deque()
        self._dibujar_marco()
        self.linea_rpm = self.create_line(0, 0, 0, 0, fill=COLORES["rpm"], width=2)
        self.linea_vel = self.create_line(0, 0, 0, 0, fill=COLORES["vel"], width=2)

    def _dibujar_marco(self):
        x0, x1 = self.IZQ, self.ANCHO - self.DER
        y0, y1 = self.ARR, self.ALTO - self.ABA
        for k in range(5):
            y = y1 - k * (y1 - y0) / 4
            self.create_line(x0, y, x1, y, fill="#ececec")
            self.create_text(x0 - 6, y, text=f"{k * self.TOPE_RPM / 4:.0f}", anchor="e",
                             font=(FUENTE, 8), fill=COLORES["rpm"])
            self.create_text(x1 + 6, y, text=f"{k * self.TOPE_KMH / 4:.0f}", anchor="w",
                             font=(FUENTE, 8), fill=COLORES["vel"])
        self.create_text(x0, self.ALTO - 8, text="rpm motor", anchor="w",
                         font=(FUENTE, 8, "bold"), fill=COLORES["rpm"])
        self.create_text(x1, self.ALTO - 8, text="km/h", anchor="e",
                         font=(FUENTE, 8, "bold"), fill=COLORES["vel"])
        self.create_text((x0 + x1) / 2, self.ALTO - 8, text=f"últimos {self.VENTANA:.0f} s",
                         font=(FUENTE, 8), fill=COLORES["tenue"])

    def limpiar(self):
        self.datos.clear()
        self.coords(self.linea_rpm, 0, 0, 0, 0)
        self.coords(self.linea_vel, 0, 0, 0, 0)

    def agregar(self, t, rpm, kmh):
        if self.datos and t - self.datos[-1][0] < 0.1:
            return
        self.datos.append((t, rpm, kmh))
        while self.datos and t - self.datos[0][0] > self.VENTANA:
            self.datos.popleft()
        if len(self.datos) >= 2:
            self._redibujar(t)

    def _redibujar(self, t_fin):
        x0, x1 = self.IZQ, self.ANCHO - self.DER
        y0, y1 = self.ARR, self.ALTO - self.ABA
        t_ini = t_fin - self.VENTANA
        px = lambda t: x0 + (t - t_ini) / self.VENTANA * (x1 - x0)
        py = lambda v, tope: y1 - min(max(v / tope, 0.0), 1.0) * (y1 - y0)
        pts_rpm, pts_vel = [], []
        for t, rpm, kmh in self.datos:
            pts_rpm += (px(t), py(rpm, self.TOPE_RPM))
            pts_vel += (px(t), py(kmh, self.TOPE_KMH))
        self.coords(self.linea_rpm, *pts_rpm)
        self.coords(self.linea_vel, *pts_vel)


class Lecturas(ttk.Frame):
    CAMPOS = {
        "motor": ("RPM", "RPM pedidas", "Cambio de rpm", "Combustible", "Torque neto",
                  "Torque máx. disp.", "Potencia"),
        "transmision": ("Marcha", "Relación", "Embrague", "Torque entrada", "Torque salida",
                        "Multiplicación", "RPM cardán", "Uso de capacidad"),
        "diferencial": ("Relación eje", "F entregada", "F requerida", "  rodadura/pend./aire",
                        "F máx. disponible", "F adherencia", "Uso de F entregada",
                        "Uso de F máxima", "Velocidad", "Aceleración"),
    }
    TITULOS = {"motor": "Motor", "transmision": "Transmisión", "diferencial": "Diferencial"}

    def __init__(self, padre):
        super().__init__(padre)
        self.vars = {}
        for col, comp in enumerate(COMPONENTES):
            caja = ttk.LabelFrame(self, text=self.TITULOS[comp], padding=(10, 4))
            caja.grid(row=0, column=col, sticky="nsew", padx=4)
            self.columnconfigure(col, weight=1)
            for fila, campo in enumerate(self.CAMPOS[comp]):
                ttk.Label(caja, text=campo, foreground=COLORES["tenue"]).grid(
                    row=fila, column=0, sticky="w")
                var = tk.StringVar(value="—")
                ttk.Label(caja, textvariable=var, font=("Consolas", 10)).grid(
                    row=fila, column=1, sticky="e", padx=(12, 0))
                self.vars[(comp, campo)] = var

    def mostrar(self, lec: Lectura):
        m, tr, b = lec.motor, lec.trans, lec.balance
        pct = lambda x: "—" if math.isinf(x) else f"{x:6.0%}"
        valores = {
            ("motor", "RPM"): f"{m.rpm:6.0f}",
            ("motor", "RPM pedidas"): f"{m.rpm_objetivo:6.0f}",
            ("motor", "Cambio de rpm"): f"{round(m.rpm_por_s):+6d} rpm/s",
            ("motor", "Combustible"): f"{m.combustible:6.0%}",
            ("motor", "Torque neto"): f"{m.torque_neto:6.0f} N·m",
            ("motor", "Torque máx. disp."): f"{m.torque_maximo:6.0f} N·m",
            ("motor", "Potencia"): f"{m.potencia_kw:6.0f} kW",
            ("transmision", "Marcha"): f"{tr.marcha:>6}",
            ("transmision", "Relación"): f"{tr.relacion:6.2f} : 1",
            ("transmision", "Embrague"): f"{tr.embrague} ({tr.deslizamiento_rpm:.0f} rpm)",
            ("transmision", "Torque entrada"): f"{tr.torque_entrada:6.0f} N·m",
            ("transmision", "Torque salida"): f"{tr.torque_salida:6.0f} N·m",
            ("transmision", "Multiplicación"): f"{tr.relacion * tr.eficiencia:6.2f} x",
            ("transmision", "RPM cardán"): f"{tr.rpm_salida:6.0f}",
            ("transmision", "Uso de capacidad"): f"{tr.uso_capacidad:6.0%}",
            ("diferencial", "Relación eje"): f"{lec.relacion_diff:6.2f} : 1",
            ("diferencial", "F entregada"): f"{b.f_entregada / 1e3:6.1f} kN",
            ("diferencial", "F requerida"): f"{b.f_requerida / 1e3:6.1f} kN",
            ("diferencial", "  rodadura/pend./aire"):
                f"{b.f_rodadura / 1e3:.1f} / {b.f_pendiente / 1e3:.1f} / {b.f_aire / 1e3:.1f}",
            ("diferencial", "F máx. disponible"): f"{b.f_maxima / 1e3:6.1f} kN",
            ("diferencial", "F adherencia"): f"{b.f_adherencia / 1e3:6.1f} kN",
            ("diferencial", "Uso de F entregada"): pct(b.uso_entregada),
            ("diferencial", "Uso de F máxima"): pct(b.uso_maxima),
            ("diferencial", "Velocidad"): f"{b.velocidad * 3.6:6.1f} km/h",
            ("diferencial", "Aceleración"): f"{round(b.aceleracion, 2) + 0.0:6.2f} m/s²",
        }
        for clave, texto in valores.items():
            self.vars[clave].set(texto)


class PanelChofer(tk.Tk):
    PERIODO_MS = 33

    def __init__(self, exe: str):
        super().__init__()
        self.title("Chofer de Springfield — tren motriz International (modelo en C)")
        self.configure(bg=COLORES["fondo"])
        self.sim = TrenMotrizC(exe)
        self.indicadores = {c: Indicador() for c in COMPONENTES}
        self.corriendo = False
        self._ultimo = time.perf_counter()
        self._estilo()
        self._construir()
        self._aplicar_configuracion()
        self._refrescar(self.sim.lectura())
        self.bind("<Up>", lambda e: self._mover_acelerador(5))
        self.bind("<Down>", lambda e: self._mover_acelerador(-5))
        self.bind("<space>", lambda e: self._alternar())
        self.protocol("WM_DELETE_WINDOW", self._cerrar)
        self.after(self.PERIODO_MS, self._ciclo)

    def _estilo(self):
        estilo = ttk.Style(self)
        if "clam" in estilo.theme_names():
            estilo.theme_use("clam")
        for nombre in ("TFrame", "TLabelframe", "TLabelframe.Label", "TLabel"):
            estilo.configure(nombre, background=COLORES["fondo"])

    def _construir(self):
        izq = ttk.Frame(self, padding=10)
        izq.grid(row=0, column=0, sticky="ns")
        der = ttk.Frame(self, padding=(0, 10, 10, 10))
        der.grid(row=0, column=1, sticky="nsew")
        self.columnconfigure(1, weight=1)
        self._construir_acelerador(izq)
        self._construir_botones(izq)
        self._construir_entradas(izq)
        self.lbl_estado = ttk.Label(izq, text="", foreground=COLORES["tenue"], padding=(0, 10))
        self.lbl_estado.grid(row=3, column=0, sticky="w")

        self.diagrama = Diagrama(der, SUBTITULOS)
        self.diagrama.grid(row=0, column=0, sticky="ew")
        self.lecturas = Lecturas(der)
        self.lecturas.grid(row=1, column=0, sticky="ew", pady=8)
        self.tendencia = Tendencia(der)
        self.tendencia.grid(row=2, column=0, sticky="ew")

    def _construir_acelerador(self, padre):
        marco = ttk.LabelFrame(padre, text="Acelerador", padding=8)
        marco.grid(row=0, column=0, sticky="ew")
        self.var_acel = tk.DoubleVar(value=0.0)
        tk.Scale(marco, from_=100, to=0, resolution=1, length=220, width=28, sliderlength=44,
                 orient="vertical",
                 variable=self.var_acel, showvalue=False, command=lambda _v: self._leer_acelerador(),
                 bg=COLORES["fondo"], highlightthickness=0, troughcolor="#e2e2e2").grid(
            row=0, column=0, rowspan=2)
        self.lbl_acel = ttk.Label(marco, text="0 %", font=(FUENTE, 20, "bold"))
        self.lbl_acel.grid(row=0, column=1, padx=12, sticky="s")
        ttk.Label(marco, text="flechas ↑ ↓\nespacio = pausa",
                  foreground=COLORES["tenue"]).grid(row=1, column=1, padx=12, sticky="n")

    def _construir_botones(self, padre):
        marco = ttk.Frame(padre, padding=(0, 10))
        marco.grid(row=1, column=0, sticky="ew")
        self.btn_correr = ttk.Button(marco, text="Arrancar", command=self._alternar)
        self.btn_correr.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(marco, text="Reiniciar", command=self._reiniciar).grid(row=0, column=1, sticky="ew")
        marco.columnconfigure((0, 1), weight=1)

    def _construir_entradas(self, padre):
        marco = ttk.LabelFrame(padre, text="Entradas fijas (en pausa)", padding=8)
        marco.grid(row=2, column=0, sticky="ew")
        self.var_masa = tk.StringVar(value="15000")
        self.var_pend = tk.StringVar(value="0")
        self.var_sup = tk.StringVar(value="Asfalto seco")
        self.var_marcha = tk.StringVar(value="1")
        self.var_rango = tk.StringVar(value="alta")
        campos = (
            ("Peso bruto [kg]", ttk.Spinbox(marco, from_=5000, to=40000, increment=500,
                                            textvariable=self.var_masa, width=10)),
            ("Pendiente [%]", ttk.Spinbox(marco, from_=-15, to=25, increment=0.5,
                                          textvariable=self.var_pend, width=10)),
            ("Superficie", ttk.Combobox(marco, values=list(SUPERFICIES), textvariable=self.var_sup,
                                        state="readonly", width=20)),
            ("Marcha", ttk.Combobox(marco, values=list(MARCHAS),
                                    textvariable=self.var_marcha, state="readonly", width=10)),
            ("Rango del eje", ttk.Combobox(marco, values=("alta", "baja"),
                                           textvariable=self.var_rango, state="readonly", width=10)),
        )
        self.entradas = []
        for fila, (texto, widget) in enumerate(campos):
            ttk.Label(marco, text=texto).grid(row=fila, column=0, sticky="w", pady=2)
            widget.grid(row=fila, column=1, sticky="ew", padx=(8, 0), pady=2)
            self.entradas.append(widget)

    def _aplicar_configuracion(self) -> bool:
        try:
            cfg = Configuracion(
                marcha=self.var_marcha.get(),
                rango=self.var_rango.get(),
                masa=float(self.var_masa.get()),
                pendiente=float(self.var_pend.get()),
                superficie=self.var_sup.get(),
            )
        except ValueError:
            messagebox.showerror("Entrada inválida", "Peso y pendiente deben ser números.")
            return False
        if cfg.masa <= 0:
            messagebox.showerror("Entrada inválida", "El peso debe ser positivo.")
            return False
        self.sim.configurar(cfg)
        return True

    def _leer_acelerador(self):
        self.sim.fijar_acelerador(self.var_acel.get() / 100.0)
        self.lbl_acel.configure(text=f"{self.var_acel.get():.0f} %")

    def _mover_acelerador(self, delta):
        self.var_acel.set(min(max(self.var_acel.get() + delta, 0), 100))
        self._leer_acelerador()

    def _habilitar_entradas(self, habilitar: bool):
        for w in self.entradas:
            if not habilitar:
                w.configure(state="disabled")
            else:
                w.configure(state="readonly" if isinstance(w, ttk.Combobox) else "normal")

    def _alternar(self):
        if self.corriendo:
            self.corriendo = False
            self.btn_correr.configure(text="Arrancar")
            self._habilitar_entradas(True)
        elif self._aplicar_configuracion():
            self.corriendo = True
            self.btn_correr.configure(text="Pausar")
            self._habilitar_entradas(False)
            self._ultimo = time.perf_counter()
        self._refrescar(self.sim.lectura())

    def _reiniciar(self):
        if self.corriendo:
            self._alternar()
        self.sim.reiniciar()
        for ind in self.indicadores.values():
            ind.reiniciar()
        self.tendencia.limpiar()
        self._refrescar(self.sim.lectura())

    def _ciclo(self):
        ahora = time.perf_counter()
        dt = min(ahora - self._ultimo, 0.1)
        self._ultimo = ahora
        if self.corriendo:
            try:
                self.sim.avanzar(dt)
                lec = self.sim.lectura()
            except RuntimeError as e:
                self.corriendo = False
                messagebox.showerror("¡D'oh!", str(e))
                return
            for c in COMPONENTES:
                self.indicadores[c].actualizar(*lec.estados[c], dt)
            self._refrescar(lec)
        self.after(self.PERIODO_MS, self._ciclo)

    def _refrescar(self, lec: Lectura):
        self.diagrama.pintar(self.indicadores, lec)
        self.lecturas.mostrar(lec)
        self.tendencia.agregar(lec.t, lec.motor.rpm, lec.balance.velocidad * 3.6)
        estado = "corriendo" if self.corriendo else "en pausa"
        self.lbl_estado.configure(text=f"t = {lec.t:6.1f} s   ({estado})")

    def _cerrar(self):
        self.sim.cerrar()
        self.destroy()


# ================================================================ entrada

def main() -> None:
    parser = argparse.ArgumentParser(description="Chofer de Springfield (modelo en C)")
    parser.add_argument("--prueba", action="store_true", help="corre los episodios en consola")
    parser.add_argument("--exe", help="ruta al ejecutable compilado de springfield.c")
    args = parser.parse_args()

    exe = encontrar_exe(args.exe)
    if exe is None:
        if args.prueba:
            sys.exit(INSTRUCCIONES_COMPILAR)
        raiz = tk.Tk()
        raiz.withdraw()
        messagebox.showerror("¡D'oh! Falta el ejecutable", INSTRUCCIONES_COMPILAR)
        raiz.destroy()
        sys.exit(1)

    if args.prueba:
        salida = subprocess.run([exe], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        print(salida.stdout.decode("utf-8", errors="replace"), end="")
    else:
        PanelChofer(exe).mainloop()


if __name__ == "__main__":
    main()
