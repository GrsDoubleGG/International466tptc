/*
 * =====================================================================
 *   EL TREN MOTRIZ DE LA FAMILIA SIMPSON
 *   International DT466E  +  Eaton Fuller RT-8908LL  +  Eaton 16244
 *
 *        _.-""""-._
 *      .'  .--.    '.
 *     /   /    \     \        "Mmm... torque."
 *    |   |      |     |
 *     \   \    /     /
 *      '.  '--'    .'
 *        '-.____.-'
 *
 *   "¡Lisa, en esta casa obedecemos las leyes de la termodinámica!"
 *                                                  -- Homero J. Simpson
 *
 *   Reparto:
 *     Motor        -> la Planta Nuclear de Springfield (combustible: rosquillas)
 *     Gobernador   -> el Sr. Burns (y Smithers lleva la cuenta: la integral)
 *     Embrague     -> la taberna de Moe (si patina mucho: Llamarada Moe)
 *     Transmisión  -> el Kwik-E-Mart de Apu (8 octillizos + 2 primos bajos)
 *     Diferencial  -> Patty y Selma (dos ruedas, un mismo mal humor)
 *     Indicadores  -> Milhouse, que tarda 0.4 s en decidirse
 *
 *   Compilar:  gcc -O2 -o springfield springfield.c -lm
 *   Correr:    ./springfield
 *   Modo para la interfaz de Python (chofer_springfield.py):
 *              ./springfield --chofer
 * =====================================================================
 */
#define _CRT_SECURE_NO_WARNINGS   /* para que Visual Studio no llore por sscanf */
#include <stdio.h>
#include <math.h>
#include <string.h>

typedef double rosquilla;      /* redonda, con un hoyo decimal en medio */
typedef const char *chisme;    /* lo que se cuenta en la barra de Moe   */
typedef int sino;              /* sí o no, como la boleta de Homero     */

#define WUJU 1
#define DOH  0
#define MULTIPLICATE_POR_CERO 0.0
#define GRAVEDAD_DE_SPRINGFIELD 9.81
#define RAD_A_RPM 9.5492965855137211
#define RPM_A_RAD (1.0 / RAD_A_RPM)
#define EL_MENOS_PEOR(a, b) ((a) < (b) ? (a) : (b))
#define EL_MAS_GORDO(a, b)  ((a) > (b) ? (a) : (b))
/* no te pases de la raya, ni por arriba ni por abajo */
#define AY_CARAMBA(x, piso, techo) EL_MAS_GORDO(piso, EL_MENOS_PEOR(techo, x))
#define TIC_TAC_DEL_RELOJ_DE_BURNS 0.001

/* ===================================================================
 *  MOTOR: la Planta Nuclear de Springfield (DT466E 225 HP)
 * =================================================================== */
#define CUANTOS_PUNTOS 10
static const rosquilla rpm_de_la_curva[CUANTOS_PUNTOS] =
    {800, 1000, 1200, 1450, 1800, 2050, 2400, 2700, 2810, 2835};
static const rosquilla torque_de_la_curva[CUANTOS_PUNTOS] =
    {542, 678, 777, 850, 862, 851, 678, 613, 407, 0};

#define RPM_RALENTI                     700.0
#define RPM_GOBERNADA                  2600.0
#define RPM_PEOR_AHOGO_DE_LA_HISTORIA   350.0
#define RPM_SOBREGIRO                  2900.0
#define INERCIA_DE_HOMERO_EN_EL_SILLON    2.5

typedef struct {
    rosquilla vueltas;           /* omega [rad/s]                         */
    rosquilla pedal_de_homero;   /* acelerador 0..1                       */
    rosquilla smithers;          /* integral del PI: siempre ahí, sumando */
    rosquilla lo_que_le_piden;   /* torque de carga                       */
    rosquilla rpm_por_s;         /* cambio de rpm, filtrado               */
    rosquilla rosquillas;        /* combustible 0..1                      */
    sino homero_se_durmio;       /* motor ahogado                         */
} PlantaNuclear;

static rosquilla curva_de_homero(rosquilla rpm)
{
    int k;
    if (rpm <= rpm_de_la_curva[0]) {
        rosquilla despertando = (rpm - RPM_PEOR_AHOGO_DE_LA_HISTORIA)
                              / (rpm_de_la_curva[0] - RPM_PEOR_AHOGO_DE_LA_HISTORIA);
        return torque_de_la_curva[0] * AY_CARAMBA(despertando, 0.0, 1.0);
    }
    if (rpm >= rpm_de_la_curva[CUANTOS_PUNTOS - 1])
        return torque_de_la_curva[CUANTOS_PUNTOS - 1];
    for (k = 1; k < CUANTOS_PUNTOS && rpm_de_la_curva[k] <= rpm; k++)
        ;   /* Ralph buscando su lugar en la fila */
    return torque_de_la_curva[k - 1]
         + (torque_de_la_curva[k] - torque_de_la_curva[k - 1])
         * (rpm - rpm_de_la_curva[k - 1]) / (rpm_de_la_curva[k] - rpm_de_la_curva[k - 1]);
}

static rosquilla friccion_de_la_barriga(rosquilla rpm)
{
    return rpm <= 0.0 ? MULTIPLICATE_POR_CERO : 35.0 + 0.025 * rpm;
}

static rosquilla rpm_de(PlantaNuclear *p) { return p->vueltas * RAD_A_RPM; }

static rosquilla lo_que_quiere_homero(PlantaNuclear *p)
{
    return RPM_RALENTI + p->pedal_de_homero * (RPM_GOBERNADA - RPM_RALENTI);
}

static rosquilla torque_neto(PlantaNuclear *p)
{
    rosquilla rpm = rpm_de(p), barriga = friccion_de_la_barriga(rpm);
    if (p->homero_se_durmio)
        return -barriga;
    return p->rosquillas * (curva_de_homero(rpm) + barriga) - barriga;
}

static rosquilla torque_maximo(PlantaNuclear *p)
{
    return p->homero_se_durmio ? 0.0 : curva_de_homero(rpm_de(p));
}

/* "Excelente..."  El gobernador PI: Burns decide cuántas rosquillas
 * le tocan a Homero y Smithers apunta todos los errores del pasado. */
static void sr_burns(PlantaNuclear *p, rosquilla dt)
{
    rosquilla rpm = rpm_de(p);
    rosquilla barriga = friccion_de_la_barriga(rpm);
    rosquilla capacidad = curva_de_homero(rpm) + barriga;
    rosquilla error, corazonada, pedido;
    sino ya_no_da_mas;

    if (capacidad <= 0.0) {
        p->rosquillas = MULTIPLICATE_POR_CERO;
        return;
    }
    error = lo_que_quiere_homero(p) - rpm;
    corazonada = (p->lo_que_le_piden + barriga) / capacidad;
    pedido = corazonada + 0.006 * error + p->smithers;
    ya_no_da_mas = (pedido >= 1.0 && error > 0.0) || (pedido <= 0.0 && error < 0.0);
    if (!ya_no_da_mas)
        p->smithers = AY_CARAMBA(p->smithers + 0.004 * error * dt, -0.3, 0.3);
    p->rosquillas = AY_CARAMBA(pedido, 0.0, 1.0);
}

static void reiniciar_planta(PlantaNuclear *p)
{
    p->vueltas = RPM_RALENTI * RPM_A_RAD;
    p->pedal_de_homero = p->smithers = p->lo_que_le_piden = 0.0;
    p->rpm_por_s = p->rosquillas = 0.0;
    p->homero_se_durmio = DOH;
    sr_burns(p, 0.0);
}

static void turno_en_la_planta(PlantaNuclear *p, rosquilla dt, rosquilla carga)
{
    rosquilla alfa, tasa, k;
    p->lo_que_le_piden = carga;
    alfa = (torque_neto(p) - carga) / INERCIA_DE_HOMERO_EN_EL_SILLON;
    p->vueltas = EL_MAS_GORDO(p->vueltas + dt * alfa, 0.0);
    tasa = alfa * RAD_A_RPM;
    k = EL_MENOS_PEOR(dt / 0.05, 1.0);
    p->rpm_por_s += k * (tasa - p->rpm_por_s);
    if (!p->homero_se_durmio && rpm_de(p) < RPM_PEOR_AHOGO_DE_LA_HISTORIA) {
        p->homero_se_durmio = WUJU;     /* Peor. Ahogo. De la historia. */
        p->rosquillas = MULTIPLICATE_POR_CERO;
    }
    if (!p->homero_se_durmio)
        sr_burns(p, dt);
}

/* ===================================================================
 *  EMBRAGUE: la taberna de Moe
 *  "Taberna de Moe, habla Moe."  Si patina demasiado: Llamarada Moe.
 * =================================================================== */
typedef struct {
    rosquilla tarro;             /* torque transmitido            */
    rosquilla resbalon;          /* w_motor - w_entrada           */
    rosquilla tiempo_patinando;
    sino ya_es_cliente;          /* acoplado                      */
} TabernaDeMoe;

static void cerrar_la_taberna(TabernaDeMoe *m)
{
    m->tarro = m->resbalon = m->tiempo_patinando = 0.0;
    m->ya_es_cliente = DOH;
}

static rosquilla cuanto_aguanta_moe(TabernaDeMoe *m, rosquilla rpm)
{
    rosquilla acople;
    if (m->ya_es_cliente)
        return 1400.0;
    acople = (rpm - 1000.0) / (1400.0 - 1000.0);
    return 1400.0 * AY_CARAMBA(acople, 0.0, 1.0);
}

static rosquilla servir_tarro(TabernaDeMoe *m, rosquilla dt,
                              rosquilla w_motor, rosquilla w_entrada,
                              rosquilla j_motor, rosquilla j_entrada,
                              rosquilla t_motor, rosquilla t_entrada)
{
    rosquilla rpm = w_motor * RAD_A_RPM, cap, k = 600.0, wm, we, s;

    m->resbalon = w_motor - w_entrada;
    if (m->ya_es_cliente && rpm < 750.0)
        m->ya_es_cliente = DOH;          /* lo sacó Moe a patadas */
    cap = cuanto_aguanta_moe(m, rpm);
    if (cap <= 0.0) {
        m->tarro = m->tiempo_patinando = 0.0;
        return 0.0;
    }
    wm = w_motor + dt * t_motor / j_motor;
    we = w_entrada + dt * t_entrada / j_entrada;
    s = (wm - we) / (1.0 + dt * k * (1.0 / j_motor + 1.0 / j_entrada));
    m->tarro = AY_CARAMBA(k * s, -cap, cap);
    if (!m->ya_es_cliente && fabs(m->resbalon) < 3.0)
        m->ya_es_cliente = WUJU;
    m->tiempo_patinando = m->ya_es_cliente ? 0.0 : m->tiempo_patinando + dt;
    return m->tarro;
}

static sino llamarada_moe(TabernaDeMoe *m) { return m->tiempo_patinando > 2.0; }

/* 0 = abierto, 1 = patinando, 2 = acoplado */
static int como_esta_moe(TabernaDeMoe *m)
{
    if (m->ya_es_cliente)
        return 2;
    return m->tarro != 0.0 ? 1 : 0;
}

/* ===================================================================
 *  TRANSMISIÓN: el Kwik-E-Mart de Apu (Fuller RT-8908LL)
 *  Apu tiene octillizos; aquí son 8 marchas + 2 primos bajos.
 *  "Gracias, vuelva pronto."
 * =================================================================== */
enum { NEUTRAL, LL, L, PRIMERA, SEGUNDA, TERCERA, CUARTA, QUINTA, SEXTA, SEPTIMA, OCTAVA };

static const rosquilla octillizos_de_apu[] = {
    0.0,      /* N : el Kwik-E-Mart cerrado (milagro)  */
    19.58,    /* LL: el primo que llegó de visita      */
    12.67,    /* L : el otro primo                     */
    8.39, 6.23, 4.58, 3.40, 2.46, 1.83, 1.35, 1.00    /* los octillizos */
};

typedef struct {
    int marcha;
    TabernaDeMoe moe;   /* sí, Moe vive dentro del Kwik-E-Mart. No preguntes. */
} KwikEMart;

static rosquilla relacion(KwikEMart *a)  { return octillizos_de_apu[a->marcha]; }
static sino en_neutral(KwikEMart *a)     { return relacion(a) == 0.0; }
static rosquilla eficiencia(KwikEMart *a) { return relacion(a) == 1.0 ? 0.99 : 0.97; }

static rosquilla torque_salida(KwikEMart *a, rosquilla t_entrada)
{
    rosquilla factor;
    if (en_neutral(a))
        return 0.0;
    factor = t_entrada >= 0.0 ? eficiencia(a) : 1.0 / eficiencia(a);
    return t_entrada * relacion(a) * factor;
}

static rosquilla velocidad_entrada(KwikEMart *a, rosquilla w_salida) { return w_salida * relacion(a); }

static rosquilla torque_reflejado_entrada(KwikEMart *a, rosquilla t_salida)
{
    return en_neutral(a) ? 0.0 : t_salida / relacion(a);
}

static rosquilla inercia_reflejada_salida(KwikEMart *a) { return 0.06 * relacion(a) * relacion(a); }

static rosquilla inercia_vista_en_entrada(KwikEMart *a, rosquilla j_salida)
{
    return en_neutral(a) ? 0.06 : 0.06 + j_salida / (relacion(a) * relacion(a));
}

/* ===================================================================
 *  DIFERENCIAL: Patty y Selma (Eaton 16244, dos velocidades)
 *  Reparten el torque entre dos ruedas con el mismo entusiasmo
 *  con el que reciben a Homero en la casa.
 * =================================================================== */
#define RADIO_DE_LLANTA            0.52
#define INERCIA_DE_LAS_RUEDAS     48.0
#define RIGIDEZ_DEL_PELO_DE_MARGE 200000.0

typedef struct {
    rosquilla kilos;                       /* masa [kg]          */
    rosquilla desfiladero_de_springfield;  /* pendiente [%]      */
    rosquilla agarre;                      /* mu                 */
    rosquilla coef_rodadura;               /* crr                */
} CargaDeBarney;

typedef struct {
    sino rango_alto;
    rosquilla vueltas_rueda, velocidad, aceleracion, torque_eje, fuerza_llanta;
    rosquilla rodadura, cuesta, viento;
    sino ay_caramba_patina;
    CargaDeBarney carga;
} PattyYSelma;

static rosquilla relacion_eje(PattyYSelma *d) { return d->rango_alto ? 4.88 : 6.55; }
static rosquilla eficiencia_eje(PattyYSelma *d) { return d->rango_alto ? 0.96 : 0.94; }
static rosquilla velocidad_cardan(PattyYSelma *d) { return d->vueltas_rueda * relacion_eje(d); }

static rosquilla torque_al_eje(PattyYSelma *d, rosquilla t_cardan)
{
    rosquilla factor = t_cardan >= 0.0 ? eficiencia_eje(d) : 1.0 / eficiencia_eje(d);
    return t_cardan * relacion_eje(d) * factor;
}

static rosquilla angulo_del_desfiladero(PattyYSelma *d)
{
    return atan(d->carga.desfiladero_de_springfield / 100.0);
}

static rosquilla fuerza_de_agarre(PattyYSelma *d)
{
    return d->carga.agarre * d->carga.kilos * GRAVEDAD_DE_SPRINGFIELD
         * cos(angulo_del_desfiladero(d)) * 0.65;
}

static rosquilla inercia_vista_en_cardan(PattyYSelma *d) { return INERCIA_DE_LAS_RUEDAS / (relacion_eje(d) * relacion_eje(d)); }
static rosquilla torque_reaccion_cardan(PattyYSelma *d) { return d->fuerza_llanta * RADIO_DE_LLANTA / relacion_eje(d); }

static void reiniciar_patty_y_selma(PattyYSelma *d)
{
    d->vueltas_rueda = d->velocidad = d->aceleracion = d->torque_eje = d->fuerza_llanta = 0.0;
    d->rodadura = d->cuesta = d->viento = 0.0;
    d->ay_caramba_patina = DOH;
}

static void lo_que_estorba(PattyYSelma *d, rosquilla v)
{
    rosquilla th = angulo_del_desfiladero(d);
    d->rodadura = d->carga.coef_rodadura * d->carga.kilos * GRAVEDAD_DE_SPRINGFIELD * cos(th) * tanh(v / 0.1);
    d->cuesta   = d->carga.kilos * GRAVEDAD_DE_SPRINGFIELD * sin(th);
    d->viento   = 0.5 * 1.05 * 6.0 * v * fabs(v);
}

static void echar_a_rodar(PattyYSelma *d, rosquilla dt, rosquilla t_cardan, rosquilla j_cardan)
{
    rosquilla r = RADIO_DE_LLANTA, m = d->carga.kilos, c = RIGIDEZ_DEL_PELO_DE_MARGE;
    rosquilla j, w_pred, v_pred, s, agarre, w_nueva, v_nueva;

    j = INERCIA_DE_LAS_RUEDAS + j_cardan * relacion_eje(d) * relacion_eje(d);
    d->torque_eje = torque_al_eje(d, t_cardan);
    lo_que_estorba(d, d->velocidad);

    w_pred = d->vueltas_rueda + dt * d->torque_eje / j;
    v_pred = d->velocidad - dt * (d->rodadura + d->cuesta + d->viento) / m;
    s = (w_pred * r - v_pred) / (1.0 + dt * c * (r * r / j + 1.0 / m));
    agarre = fuerza_de_agarre(d);
    d->ay_caramba_patina = fabs(c * s) > agarre;
    d->fuerza_llanta = AY_CARAMBA(c * s, -agarre, agarre);

    w_nueva = w_pred - dt * d->fuerza_llanta * r / j;
    v_nueva = v_pred + dt * d->fuerza_llanta / m;
    if (v_nueva < 0.0) {           /* anti-retroceso: el camión no se va de reversa */
        v_nueva = 0.0;
        w_nueva = EL_MAS_GORDO(w_nueva, 0.0);
    }
    d->aceleracion = (v_nueva - d->velocidad) / dt;
    d->vueltas_rueda = w_nueva;
    d->velocidad = v_nueva;
}

/* ===================================================================
 *  INDICADORES: Milhouse tarda 0.4 s en cambiar de opinión
 * =================================================================== */
enum { ECHADO_EN_EL_SILLON, TODO_EXCELENTE, ALERTA_EN_EL_SECTOR_7G };
static chisme como_le_va[] = {"underload", "stable", "overload"};

typedef struct {
    int opinion;
    rosquilla dudando;
    int candidata;
} Milhouse;

static void milhouse_despierta(Milhouse *m)
{
    m->opinion = TODO_EXCELENTE;
    m->dudando = 0.0;
    m->candidata = -1;
}

static void milhouse_decide(Milhouse *m, int que_paso, rosquilla dt)
{
    if (que_paso == m->opinion) {
        m->candidata = -1;
        return;
    }
    if (que_paso != m->candidata) {
        m->candidata = que_paso;
        m->dudando = 0.0;
    }
    m->dudando += dt;
    if (m->dudando >= 0.4) {     /* "¡Todos dicen que soy guapo!" */
        m->opinion = que_paso;
        m->candidata = -1;
    }
}

/* ===================================================================
 *  DIAGNÓSTICOS (con frase incluida, cortesía del elenco)
 * =================================================================== */
static int diagnostico_burns(PlantaNuclear *p, chisme *frase)
{
    rosquilla rpm = rpm_de(p);
    if (p->homero_se_durmio) {
        *frase = "Peor. Ahogo. De la historia. (motor ahogado)";
        return ALERTA_EN_EL_SECTOR_7G;
    }
    if (rpm > RPM_SOBREGIRO) {
        *frase = "¡La carga arrastra a Homero cuesta abajo! (sobregiro)";
        return ALERTA_EN_EL_SECTOR_7G;
    }
    if (p->rosquillas >= 0.97 && rpm < lo_que_quiere_homero(p) - 150.0) {
        if (p->rpm_por_s < 10.0) {
            *frase = "Intentar es el primer paso hacia el fracaso (a tope y no alcanza las rpm)";
            return ALERTA_EN_EL_SECTOR_7G;
        }
        *frase = "¡Wuju! A plena carga, ganando rpm";
        return TODO_EXCELENTE;
    }
    if (p->rosquillas < 0.25) {
        *frase = "Mmm... rosquillas. (carga ligera, Homero en el sillón)";
        return ECHADO_EN_EL_SILLON;
    }
    *frase = "Excelente... (sostiene las rpm pedidas)";
    return TODO_EXCELENTE;
}

static int diagnostico_apu(KwikEMart *a, rosquilla rpm_motor, rosquilla rosquillas, chisme *frase)
{
    rosquilla uso;
    if (en_neutral(a)) {
        *frase = "Gracias, vuelva pronto. (en neutral)";
        return ECHADO_EN_EL_SILLON;
    }
    uso = fabs(a->moe.tarro) / 1166.0;
    if (uso > 0.95) {
        *frase = "¡Apu, se va a tronar el changarro! (torque de entrada sobre la capacidad)";
        return ALERTA_EN_EL_SECTOR_7G;
    }
    if (llamarada_moe(&a->moe)) {
        *frase = "¡Llamarada Moe! (el embrague se está quemando)";
        return ALERTA_EN_EL_SECTOR_7G;
    }
    if (rpm_motor < 1150.0 && rosquillas >= 0.95) {
        *frase = "¡Multiplícate, Apu! (marcha larga, falta multiplicación)";
        return ALERTA_EN_EL_SECTOR_7G;
    }
    if (uso < 0.05) {
        *frase = "Más aburrido que discurso de Skinner (casi sin torque)";
        return ECHADO_EN_EL_SILLON;
    }
    if (rpm_motor > 2300.0 && rosquillas < 0.5) {
        *frase = "Marcha corta: ya puedes subir, como Bart al desfiladero";
        return ECHADO_EN_EL_SILLON;
    }
    *frase = "Hola holita, multiplicación adecuadita";
    return TODO_EXCELENTE;
}

static int diagnostico_patty_y_selma(PattyYSelma *d, rosquilla f_entregada, rosquilla f_requerida, chisme *frase)
{
    rosquilla tolerancia = d->carga.kilos * 0.05;
    if (d->ay_caramba_patina) {
        *frase = "¡Ay, caramba! (patina: el piso no sostiene la fuerza)";
        return ALERTA_EN_EL_SECTOR_7G;
    }
    if (f_requerida > f_entregada + tolerancia) {
        *frase = "¡D'oh! (requiere más fuerza, pierde velocidad)";
        return ALERTA_EN_EL_SECTOR_7G;
    }
    if (f_entregada > f_requerida + tolerancia) {
        *frase = "¡Cowabunga! (sobra fuerza, gana velocidad)";
        return ECHADO_EN_EL_SILLON;
    }
    *frase = "Fuerza justa, aprobado por Lisa";
    return TODO_EXCELENTE;
}

/* ===================================================================
 *  LA FAMILIA COMPLETA (el tren motriz acoplado)
 * =================================================================== */
typedef struct {
    PlantaNuclear planta;
    KwikEMart apu;
    PattyYSelma patty_y_selma;
    rosquilla reloj;
    rosquilla pedal;
} FamiliaSimpson;

static void configurar(FamiliaSimpson *f, int marcha, sino rango_alto,
                       rosquilla kilos, rosquilla pendiente, rosquilla agarre, rosquilla rodadura)
{
    if (marcha != f->apu.marcha)
        f->apu.moe.ya_es_cliente = DOH;   /* cambiar de marcha = soltar el embrague */
    f->apu.marcha = marcha;
    f->patty_y_selma.rango_alto = rango_alto;
    f->patty_y_selma.carga.kilos = kilos;
    f->patty_y_selma.carga.desfiladero_de_springfield = pendiente;
    f->patty_y_selma.carga.agarre = agarre;
    f->patty_y_selma.carga.coef_rodadura = rodadura;
}

static void reiniciar_familia(FamiliaSimpson *f)
{
    reiniciar_planta(&f->planta);
    cerrar_la_taberna(&f->apu.moe);
    reiniciar_patty_y_selma(&f->patty_y_selma);
    f->reloj = 0.0;
    f->planta.pedal_de_homero = f->pedal;
}

static void pisar_pedal(FamiliaSimpson *f, rosquilla cuanto)
{
    f->pedal = AY_CARAMBA(cuanto, 0.0, 1.0);
    f->planta.pedal_de_homero = f->pedal;
}

static void un_tic_de_springfield(FamiliaSimpson *f, rosquilla dt)
{
    PlantaNuclear *homero = &f->planta;
    KwikEMart *apu = &f->apu;
    PattyYSelma *ps = &f->patty_y_selma;
    rosquilla tarro;

    if (en_neutral(apu)) {
        cerrar_la_taberna(&apu->moe);
        tarro = 0.0;
    } else {
        rosquilla w_in = velocidad_entrada(apu, velocidad_cardan(ps));
        rosquilla j_in = inercia_vista_en_entrada(apu, inercia_vista_en_cardan(ps));
        rosquilla t_in = -torque_reflejado_entrada(apu, torque_reaccion_cardan(ps));
        tarro = servir_tarro(&apu->moe, dt, homero->vueltas, w_in,
                             INERCIA_DE_HOMERO_EN_EL_SILLON, j_in, torque_neto(homero), t_in);
    }
    turno_en_la_planta(homero, dt, tarro);
    echar_a_rodar(ps, dt, torque_salida(apu, tarro), inercia_reflejada_salida(apu));
    f->reloj += dt;
}

static void avanza_la_trama(FamiliaSimpson *f, rosquilla duracion)
{
    /* rint redondea al par, igual que round() de Python */
    int n = EL_MAS_GORDO(1, (int)rint(duracion / TIC_TAC_DEL_RELOJ_DE_BURNS)), i;
    for (i = 0; i < n; i++)
        un_tic_de_springfield(f, TIC_TAC_DEL_RELOJ_DE_BURNS);
}

static rosquilla fuerza_maxima(FamiliaSimpson *f)
{
    return torque_al_eje(&f->patty_y_selma, torque_salida(&f->apu, torque_maximo(&f->planta)))
         / RADIO_DE_LLANTA;
}

/* ===================================================================
 *  MODO CHOFER: el Python manda órdenes por stdin, una por línea,
 *  y el C contesta SIEMPRE con una línea de estado:
 *
 *    config <marcha 0..10> <rango_alto 0/1> <kg> <pendiente %> <mu> <crr>
 *    pedal <0..1>
 *    avanza <segundos>
 *    reinicia
 *    lee
 *    adios            (esta no contesta: Moe cuelga el teléfono)
 *
 *  Respuesta: 34 números separados por espacios y luego |frase|frase|frase
 * =================================================================== */
static void chismear_todo(FamiliaSimpson *f)
{
    PlantaNuclear *h = &f->planta;
    KwikEMart *a = &f->apu;
    PattyYSelma *ps = &f->patty_y_selma;
    chisme frase_burns, frase_apu, frase_ps;
    rosquilla f_ent = ps->torque_eje / RADIO_DE_LLANTA;
    rosquilla f_req = ps->rodadura + ps->cuesta + ps->viento;
    rosquilla t_neto = torque_neto(h);
    rosquilla v[34];
    int n = 0, i;

    v[n++] = f->reloj;                                   /*  0 t               */
    v[n++] = f->pedal;                                   /*  1 acelerador      */
    v[n++] = rpm_de(h);                                  /*  2 rpm             */
    v[n++] = lo_que_quiere_homero(h);                    /*  3 rpm objetivo    */
    v[n++] = h->rosquillas;                              /*  4 combustible     */
    v[n++] = t_neto;                                     /*  5 torque neto     */
    v[n++] = torque_maximo(h);                           /*  6 torque máximo   */
    v[n++] = h->lo_que_le_piden;                         /*  7 torque de carga */
    v[n++] = t_neto * h->vueltas / 1000.0;               /*  8 potencia kW     */
    v[n++] = h->rpm_por_s;                               /*  9 rpm/s           */
    v[n++] = h->homero_se_durmio;                        /* 10 apagado         */
    v[n++] = a->marcha;                                  /* 11 marcha          */
    v[n++] = relacion(a);                                /* 12 relación        */
    v[n++] = eficiencia(a);                              /* 13 eficiencia      */
    v[n++] = a->moe.tarro;                               /* 14 torque entrada  */
    v[n++] = torque_salida(a, a->moe.tarro);             /* 15 torque salida   */
    v[n++] = velocidad_cardan(ps) * RAD_A_RPM;           /* 16 rpm cardán      */
    v[n++] = fabs(a->moe.tarro) / 1166.0;                /* 17 uso capacidad   */
    v[n++] = a->moe.resbalon * RAD_A_RPM;                /* 18 desliz. rpm     */
    v[n++] = como_esta_moe(&a->moe);                     /* 19 embrague        */
    v[n++] = relacion_eje(ps);                           /* 20 relación eje    */
    v[n++] = ps->torque_eje;                             /* 21 torque eje      */
    v[n++] = f_ent;                                      /* 22 F entregada     */
    v[n++] = f_req;                                      /* 23 F requerida     */
    v[n++] = ps->rodadura;                               /* 24 F rodadura      */
    v[n++] = ps->cuesta;                                 /* 25 F pendiente     */
    v[n++] = ps->viento;                                 /* 26 F aire          */
    v[n++] = fuerza_maxima(f);                           /* 27 F máxima        */
    v[n++] = fuerza_de_agarre(ps);                       /* 28 F adherencia    */
    v[n++] = ps->velocidad;                              /* 29 velocidad m/s   */
    v[n++] = ps->aceleracion;                            /* 30 aceleración     */
    v[n++] = diagnostico_burns(h, &frase_burns);         /* 31 estado motor    */
    v[n++] = diagnostico_apu(a, rpm_de(h), h->rosquillas, &frase_apu);   /* 32 */
    v[n++] = diagnostico_patty_y_selma(ps, f_ent, f_req, &frase_ps);     /* 33 */

    for (i = 0; i < n; i++)
        printf(i ? " %.17g" : "%.17g", v[i]);
    printf("|%s|%s|%s\n", frase_burns, frase_apu, frase_ps);
    fflush(stdout);
}

static void modo_chofer(void)
{
    FamiliaSimpson f;
    char linea[256], orden[32];

    memset(&f, 0, sizeof f);
    configurar(&f, PRIMERA, WUJU, 15000.0, 0.0, 0.70, 0.007);
    reiniciar_familia(&f);

    while (fgets(linea, sizeof linea, stdin)) {
        if (sscanf(linea, "%31s", orden) != 1)
            continue;
        if (!strcmp(orden, "config")) {
            int marcha, alto;
            rosquilla kg, pend, mu, crr;
            if (sscanf(linea, "%*s %d %d %lf %lf %lf %lf", &marcha, &alto, &kg, &pend, &mu, &crr) == 6
                && marcha >= NEUTRAL && marcha <= OCTAVA)
                configurar(&f, marcha, alto != 0, kg, pend, mu, crr);
        } else if (!strcmp(orden, "pedal")) {
            rosquilla x;
            if (sscanf(linea, "%*s %lf", &x) == 1)
                pisar_pedal(&f, x);
        } else if (!strcmp(orden, "avanza")) {
            rosquilla x;
            if (sscanf(linea, "%*s %lf", &x) == 1)
                avanza_la_trama(&f, x);
        } else if (!strcmp(orden, "reinicia")) {
            reiniciar_familia(&f);
        } else if (!strcmp(orden, "adios")) {
            break;
        }
        chismear_todo(&f);   /* "lee" o cualquier otra cosa: solo chismea */
    }
}

/* ===================================================================
 *  EPISODIOS (sin interfaz; la tabla sale igualita que en Python)
 * =================================================================== */
static void episodio(chisme sinopsis, chisme titulo, int marcha, sino rango_alto,
                     rosquilla kilos, rosquilla pendiente, rosquilla agarre, rosquilla rodadura,
                     rosquilla pedal, rosquilla duracion)
{
    FamiliaSimpson f;
    Milhouse m_burns, m_apu, m_ps;
    chisme frase_burns = "", frase_apu = "", frase_ps = "";
    rosquilla cada_cuanto = 0.033, proxima_foto = 0.0;

    memset(&f, 0, sizeof f);
    configurar(&f, marcha, rango_alto, kilos, pendiente, agarre, rodadura);
    reiniciar_familia(&f);
    pisar_pedal(&f, pedal);
    milhouse_despierta(&m_burns);
    milhouse_despierta(&m_apu);
    milhouse_despierta(&m_ps);

    fflush(stdout);
    fprintf(stderr, "\n>> %s\n", sinopsis);
    printf("\n%s\n", titulo);
    printf("%5s %5s %6s %5s %6s %7s %7s %7s %6s %10s %10s %10s\n",
           "t", "acel", "rpm", "comb", "Tmot", "Tcard", "Fent", "Freq", "km/h",
           "motor", "trans", "diff");

    while (f.reloj < duracion - 1e-9) {
        PlantaNuclear *homero = &f.planta;
        PattyYSelma *ps = &f.patty_y_selma;
        rosquilla f_entregada, f_requerida;

        pisar_pedal(&f, pedal);
        avanza_la_trama(&f, cada_cuanto);

        f_entregada = ps->torque_eje / RADIO_DE_LLANTA;
        f_requerida = ps->rodadura + ps->cuesta + ps->viento;
        milhouse_decide(&m_burns, diagnostico_burns(homero, &frase_burns), cada_cuanto);
        milhouse_decide(&m_apu, diagnostico_apu(&f.apu, rpm_de(homero), homero->rosquillas, &frase_apu), cada_cuanto);
        milhouse_decide(&m_ps, diagnostico_patty_y_selma(ps, f_entregada, f_requerida, &frase_ps), cada_cuanto);

        if (f.reloj >= proxima_foto - 1e-9) {
            proxima_foto += 1.0;
            printf("%5.1f %4.0f%% %6.0f %5.2f %6.0f %7.0f %6.1fk %6.1fk %6.1f %10s %10s %10s\n",
                   f.reloj, f.pedal * 100.0, rpm_de(homero), homero->rosquillas,
                   torque_neto(homero), torque_salida(&f.apu, f.apu.moe.tarro),
                   f_entregada / 1e3, f_requerida / 1e3, ps->velocidad * 3.6,
                   como_le_va[m_burns.opinion], como_le_va[m_apu.opinion], como_le_va[m_ps.opinion]);
        }
    }
    fflush(stdout);
    fprintf(stderr, "   Burns:         %s\n   Apu:           %s\n   Patty y Selma: %s\n",
            frase_burns, frase_apu, frase_ps);
}

int main(int argc, char **argv)
{
    if (argc > 1 && !strcmp(argv[1], "--chofer")) {
        modo_chofer();
        return 0;
    }

    fprintf(stderr, "¡Wuju! Arranca el tren motriz de Springfield.\n");

    episodio("Episodio 1: Homero va por rosquillas al Lard Lad, en plano y con calma.",
             "Configuracion(marcha='1', rango='alta', masa=15000.0, pendiente=0.0, superficie='Asfalto seco')",
             PRIMERA, WUJU, 15000.0, 0.0, 0.70, 0.007, 0.6, 10.0);

    episodio("Episodio 2: 22 toneladas subiendo al Monte Springfield en tercera.",
             "Configuracion(marcha='3', rango='alta', masa=22000.0, pendiente=12.0, superficie='Asfalto seco')",
             TERCERA, WUJU, 22000.0, 12.0, 0.70, 0.007, 1.0, 12.0);

    episodio("Episodio 3: atascados en el lodo de la granja de tomaco.",
             "Configuracion(marcha='LL', rango='baja', masa=20000.0, pendiente=20.0, superficie='Terracería mojada / lodo')",
             LL, DOH, 20000.0, 20.0, 0.30, 0.050, 1.0, 6.0);

    fprintf(stderr, "\nMmm... simulación. Fin del episodio.\n");
    return 0;
}
