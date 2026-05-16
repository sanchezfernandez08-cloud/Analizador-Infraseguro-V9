"""
CALCULADORA DE VALOR DE RECONSTRUCCIÓN — SEGUROS CHILE
Conforme DFL 251, DS 1055, CCom art. 553, Ley 21.442 y NCG 556 CMF (dic. 2025)

Instalar: pip install streamlit pandas requests
Correr:   streamlit run app.py
Secrets (Streamlit Cloud): GOOGLE_MAPS_API_KEY = "AIza..."
"""

import streamlit as st
import pandas as pd
import requests
from datetime import date
from urllib.parse import quote

# ─────────────────────────────────────────────────────────
# PARÁMETROS
# ─────────────────────────────────────────────────────────
FACTOR_GEOGRAFICO = {
    "Metropolitana (RM y ciudades grandes)": 1.05,
    "Intermedia (ciudades medianas)":        1.00,
    "Aislada (zonas rurales o extremas)":    1.15,
}
SISTEMAS_POR_TIPO = {
    "Casa":      ["Albañilería", "Metalcon"],
    "Depto":     ["Hormigón"],
    "Edificio":  ["Hormigón"],
    "Comunidad": ["Hormigón"],
}
NIVELES_POR_TS = {
    ("Casa","Albañilería"): ["Básico","Medio","Alto"],
    ("Casa","Metalcon"):    ["Básico","Medio"],
    ("Depto","Hormigón"):   ["Medio","Alto"],
    ("Edificio","Hormigón"):["Medio","Alto"],
    ("Comunidad","Hormigón"):["Medio","Alto"],
}
COSTOS_IND = {
    "Diseño del proyecto":      0.03,
    "Gastos generales de obra": 0.06,
    "Utilidad del contratista": 0.12,
    "Imprevistos":              0.10,
}
TASA_IVA = 0.19

ZONA_CORTA = {
    "Metropolitana (RM y ciudades grandes)": "Metropolitana",
    "Intermedia (ciudades medianas)":        "Intermedia",
    "Aislada (zonas rurales o extremas)":    "Aislada",
}
TS_LABEL = {
    ("Casa","Albañilería"):  "Casa / Albañilería",
    ("Casa","Metalcon"):     "Casa / Metalcon",
    ("Depto","Hormigón"):    "Depto / Hormigón",
    ("Edificio","Hormigón"): "Edificio / Hormigón",
    ("Comunidad","Hormigón"):"Comunidad / Hormigón",
}

# VUB referencias de mercado 2025-2026 (UF/m²)
REFS_VUB = {
    ("Metropolitana","Casa / Albañilería"):  {"Básico":(18,22),"Medio":(23,30),"Alto":(31,42)},
    ("Metropolitana","Casa / Metalcon"):     {"Básico":(16,20),"Medio":(21,28),"Alto":None},
    ("Metropolitana","Depto / Hormigón"):    {"Básico":None,   "Medio":(25,33),"Alto":(34,48)},
    ("Metropolitana","Edificio / Hormigón"): {"Básico":None,   "Medio":(26,35),"Alto":(36,52)},
    ("Metropolitana","Comunidad / Hormigón"):{"Básico":None,   "Medio":(25,34),"Alto":(35,50)},
    ("Intermedia","Casa / Albañilería"):     {"Básico":(17,21),"Medio":(22,29),"Alto":(30,40)},
    ("Intermedia","Casa / Metalcon"):        {"Básico":(15,19),"Medio":(20,27),"Alto":None},
    ("Intermedia","Depto / Hormigón"):       {"Básico":None,   "Medio":(24,32),"Alto":(33,46)},
    ("Intermedia","Edificio / Hormigón"):    {"Básico":None,   "Medio":(25,34),"Alto":(35,50)},
    ("Intermedia","Comunidad / Hormigón"):   {"Básico":None,   "Medio":(24,33),"Alto":(34,48)},
    ("Aislada","Casa / Albañilería"):        {"Básico":(20,26),"Medio":(27,36),"Alto":(37,50)},
    ("Aislada","Casa / Metalcon"):           {"Básico":(18,23),"Medio":(24,32),"Alto":None},
    ("Aislada","Depto / Hormigón"):          {"Básico":None,   "Medio":(29,38),"Alto":(39,55)},
    ("Aislada","Edificio / Hormigón"):       {"Básico":None,   "Medio":(30,40),"Alto":(41,58)},
    ("Aislada","Comunidad / Hormigón"):      {"Básico":None,   "Medio":(29,39),"Alto":(40,56)},
}

# ─────────────────────────────────────────────────────────
# MOTOR DE CÁLCULO
# ─────────────────────────────────────────────────────────
def factor_normativo(anio):
    if anio < 1985:  return 1.15
    if anio <= 2000: return 1.10
    if anio <= 2010: return 1.05
    return 1.00

def factor_altura(pisos):
    if pisos <= 2:  return 1.00
    if pisos <= 5:  return 1.05
    if pisos <= 10: return 1.10
    return 1.15

def calcular_vr(vub, sup, zona_label, pisos, anio, aplica_iva):
    fg = FACTOR_GEOGRAFICO[zona_label]
    fn = factor_normativo(anio)
    fa = factor_altura(pisos)
    cd = sup * vub * fg * fn * fa
    ind_det = {k: cd * v for k, v in COSTOS_IND.items()}
    ci = sum(ind_det.values())
    st_ = cd + ci
    iv = st_ * TASA_IVA if aplica_iva else 0.0
    return {"vub":vub,"fg":fg,"fn":fn,"fa":fa,"cd":cd,
            "ind_det":ind_det,"ci":ci,"st":st_,"iv":iv,
            "aplica_iva":aplica_iva,"vr":st_+iv}

def evaluar(monto, vr):
    if monto <= 0 or vr <= 0: return 0.0, False
    r = monto / vr
    return r, r < 1.0

def indemn(danio, monto, vr):
    ratio, infra = evaluar(monto, vr)
    return danio * ratio if infra else danio

# ─────────────────────────────────────────────────────────
# GOOGLE MAPS (opcional)
# ─────────────────────────────────────────────────────────
def get_gmaps_key():
    try:
        return st.secrets.get("GOOGLE_MAPS_API_KEY", "")
    except Exception:
        return ""

def geocodificar(direccion, api_key):
    try:
        r = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": direccion + ", Chile", "key": api_key},
            timeout=6,
        )
        data = r.json()
        if data.get("status") == "OK":
            loc = data["results"][0]["geometry"]["location"]
            return loc["lat"], loc["lng"], data["results"][0]["formatted_address"]
    except Exception:
        pass
    return None

# ─────────────────────────────────────────────────────────
# WIDGETS UI
# ─────────────────────────────────────────────────────────
def widget_vub(prefix, zona_label, tipo, sis, niv):
    """
    Muestra tabla de referencia VUB para la zona/tipo/nivel seleccionado
    y luego el campo de ingreso. La tabla aparece ANTES del campo.
    """
    zc  = ZONA_CORTA.get(zona_label, "")
    ts  = TS_LABEL.get((tipo, sis), "")
    ref = REFS_VUB.get((zc, ts), {})
    rng = ref.get(niv)

    # ── Tabla de referencia VUB (aparece ANTES del campo) ──
    filas_ref = [
        {"Nivel": nv, "Mín (UF/m²)": rg[0], "Máx (UF/m²)": rg[1],
         "Promedio ref.": round((rg[0]+rg[1])/2, 1),
         "Seleccionado": "✅" if nv == niv else ""}
        for nv, rg in (ref.items() if ref else {}.items())
        if rg
    ]

    with st.expander(
        f"📊 Tabla de referencia VUB — {tipo} / {sis} / zona {zc}",
        expanded=True,
    ):
        st.caption(
            "Rangos estimados de mercado 2025–2026. **No son valores oficiales.** "
            "Para el valor exacto consulte la tabla MINVU (en pesos, trimestral): "
            "[minvu.gob.cl](https://www.minvu.gob.cl/elementos-tecnicos/tabla-de-costos-unitarios/) "
            "o un tasador / corredor habilitado."
        )
        if filas_ref:
            st.dataframe(
                pd.DataFrame(filas_ref),
                use_container_width=True,
                hide_index=True,
            )
            if rng:
                prom = round((rng[0] + rng[1]) / 2, 1)
                st.info(
                    f"Para **{niv}** en zona **{zc}**: rango **{rng[0]}–{rng[1]} UF/m²** "
                    f"· promedio referencial **{prom} UF/m²**"
                )
        else:
            st.warning("Sin datos de referencia disponibles para esta combinación.")

    # ── Campo de ingreso VUB (aparece DESPUÉS de la tabla) ──
    ph = f"Ej: {round((rng[0]+rng[1])/2,1)} (rango {rng[0]}–{rng[1]})" if rng else "Ej: 28.0"
    return st.number_input(
        "VUB — Valor Unitario Base (UF/m²)",
        min_value=1.0, max_value=200.0, value=None,
        step=0.5, format="%.1f", placeholder=ph,
        key=f"{prefix}_vub",
        help="Ingrese el VUB según tasador, corredor de seguros o tabla MINVU convertida a UF.",
    )


def widget_tabla_refs_vub(zona_label):
    """Tabla completa de referencias VUB para la zona seleccionada."""
    zc = ZONA_CORTA.get(zona_label, "")
    filas = [
        {"Tipo / Sistema": ts, "Nivel": nv,
         "Mín (UF/m²)": rg[0], "Máx (UF/m²)": rg[1],
         "Promedio ref.": round((rg[0]+rg[1])/2, 1)}
        for (zc2, ts), nivs in REFS_VUB.items()
        if zc2 == zc
        for nv, rg in nivs.items()
        if rg
    ]
    if filas:
        with st.expander(f"📋 Ver tabla completa de referencias VUB — zona {zc}", expanded=False):
            st.caption("Estimaciones de mercado 2025–2026. No son valores oficiales. "
                       "Tabla MINVU (en pesos): https://www.minvu.gob.cl/elementos-tecnicos/tabla-de-costos-unitarios/")
            st.dataframe(
                pd.DataFrame(filas).sort_values(["Tipo / Sistema","Nivel"]),
                use_container_width=True, hide_index=True,
            )


def widget_distribucion_superficies(sup_total):
    """
    Panel visual completo de distribución bienes comunes / unidades privadas.
    Retorna (pct_comun_decimal, sup_comun_m2, sup_units_m2).
    """
    st.markdown("#### Distribución de superficies: bienes comunes vs unidades privadas")

    # ── Tabla de rangos referenciales ──
    st.markdown(
        "No existe un porcentaje único fijado por ley — cada edificio lo define en su "
        "**Reglamento de Copropiedad**. Use la tabla siguiente como referencia:"
    )

    tabla_html = """
<style>
.dist-table {width:100%;border-collapse:collapse;font-size:13px;margin-bottom:12px}
.dist-table th {background:#f0f2f6;padding:7px 10px;text-align:left;border-bottom:2px solid #ddd;font-weight:600}
.dist-table td {padding:6px 10px;border-bottom:1px solid #eee;vertical-align:top}
.dist-table tr:last-child td {background:#e8f4e8;font-weight:600}
.pct-comun {color:#1f77b4;font-weight:700;text-align:center}
.pct-units {color:#e67e22;font-weight:700;text-align:center}
.badge {display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600}
.b-blue {background:#dbeafe;color:#1d4ed8}
.b-orange {background:#fef3c7;color:#92400e}
.b-green {background:#d1fae5;color:#065f46}
</style>
<table class="dist-table">
  <tr>
    <th>Tipo de edificio</th>
    <th>Bienes comunes</th>
    <th>Unidades privadas</th>
    <th>Descripción</th>
  </tr>
  <tr>
    <td>🏢 Básico<br><small>2–5 pisos · sin amenidades</small></td>
    <td class="pct-comun"><span class="badge b-blue">25 – 35 %</span></td>
    <td class="pct-units"><span class="badge b-orange">65 – 75 %</span></td>
    <td><small>Pasillos, escaleras y conserjería básica. Sin subterráneos ni amenidades.</small></td>
  </tr>
  <tr>
    <td>🏢 Estándar<br><small>6–15 pisos · 1 subterráneo</small></td>
    <td class="pct-comun"><span class="badge b-blue">35 – 45 %</span></td>
    <td class="pct-units"><span class="badge b-orange">55 – 65 %</span></td>
    <td><small>Piscina, gimnasio, sala multiuso y 1 nivel de estacionamientos.</small></td>
  </tr>
  <tr>
    <td>🏢 Alto estándar<br><small>15–25 pisos · 2 subterráneos</small></td>
    <td class="pct-comun"><span class="badge b-blue">45 – 55 %</span></td>
    <td class="pct-units"><span class="badge b-orange">45 – 55 %</span></td>
    <td><small>Múltiples amenidades, lobby amplio, 2 niveles de estacionamientos.</small></td>
  </tr>
  <tr>
    <td>🏢 Premium / Torre<br><small>25+ pisos · 3+ subterráneos</small></td>
    <td class="pct-comun"><span class="badge b-blue">55 – 70 %</span></td>
    <td class="pct-units"><span class="badge b-orange">30 – 45 %</span></td>
    <td><small>Todas las amenidades, lobby doble altura, spa, múltiples subterráneos.</small></td>
  </tr>
  <tr>
    <td>📋 Referencia Ley 21.442</td>
    <td class="pct-comun"><span class="badge b-green">50 – 70 %</span><br><small>del VR total</small></td>
    <td class="pct-units">—</td>
    <td><small>Bienes comunes representan 50–70% del <strong>valor</strong> de reconstrucción (no solo superficie).</small></td>
  </tr>
</table>
<p style="font-size:11px;color:#888;margin-top:-8px">
Fuentes: Edifito / Ley 21.442 · ComunidadFeliz · OGUC art. 5.1.11 · Práctica de mercado 2025–2026
</p>
"""
    st.markdown(tabla_html, unsafe_allow_html=True)

    # ── Slider de selección ──
    pct_pct = st.slider(
        "Seleccione el % de superficie de bienes comunes para este edificio",
        min_value=20, max_value=70, value=40, step=1,
        help="Use la tabla anterior como guía. Para el valor exacto consulte el Reglamento de Copropiedad.",
        key="pct_comun_slider",
    )
    pct = pct_pct / 100

    # ── Barra visual proporcional ──
    bar_html = f"""
<div style="margin:8px 0 4px 0">
  <div style="display:flex;height:28px;border-radius:6px;overflow:hidden;border:1px solid #ddd">
    <div style="width:{pct_pct}%;background:#1f77b4;display:flex;align-items:center;
                justify-content:center;color:white;font-size:12px;font-weight:600;
                min-width:30px;transition:width 0.3s">
      {pct_pct}%
    </div>
    <div style="width:{100-pct_pct}%;background:#e67e22;display:flex;align-items:center;
                justify-content:center;color:white;font-size:12px;font-weight:600;
                min-width:30px;transition:width 0.3s">
      {100-pct_pct}%
    </div>
  </div>
  <div style="display:flex;gap:20px;margin-top:5px;font-size:12px">
    <span style="color:#1f77b4">■ Bienes comunes: <strong>{pct_pct}%</strong></span>
    <span style="color:#e67e22">■ Unidades privadas: <strong>{100-pct_pct}%</strong></span>
  </div>
</div>
"""
    st.markdown(bar_html, unsafe_allow_html=True)
    st.caption("⚠️ Distribución estimada. Para el valor exacto use el Reglamento de Copropiedad "
               "o los planos de arquitectura del edificio.")

    # ── Desglose en m² ──
    sup_comun = None
    sup_units = None
    if sup_total:
        sup_comun = round(sup_total * pct)
        sup_units = sup_total - sup_comun

        desglose_html = f"""
<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin:10px 0">
  <div style="background:#f8f9fa;border-radius:8px;padding:12px;border-left:4px solid #888;text-align:center">
    <div style="font-size:11px;color:#666;margin-bottom:4px">Superficie total</div>
    <div style="font-size:20px;font-weight:600">{sup_total:,.0f} m²</div>
  </div>
  <div style="background:#dbeafe;border-radius:8px;padding:12px;border-left:4px solid #1f77b4;text-align:center">
    <div style="font-size:11px;color:#1d4ed8;margin-bottom:4px">Bienes comunes ({pct_pct}%)</div>
    <div style="font-size:20px;font-weight:600;color:#1d4ed8">{sup_comun:,.0f} m²</div>
  </div>
  <div style="background:#fef3c7;border-radius:8px;padding:12px;border-left:4px solid #e67e22;text-align:center">
    <div style="font-size:11px;color:#92400e;margin-bottom:4px">Unidades privadas ({100-pct_pct}%)</div>
    <div style="font-size:20px;font-weight:600;color:#92400e">{sup_units:,.0f} m²</div>
  </div>
</div>
"""
        st.markdown(desglose_html, unsafe_allow_html=True)

    return pct, sup_comun, sup_units


def widget_herramienta_direccion(direccion):
    """
    Herramienta de apoyo para medir superficie desde dirección.
    Funciona con o sin API key de Google Maps.
    """
    if not direccion.strip():
        return

    with st.expander("🗺️ Herramienta de apoyo — Medir superficie desde dirección", expanded=False):
        st.markdown(
            "Use estas herramientas para estimar la **planta del edificio** "
            "y luego multiplíquela por el número de pisos + subterráneos."
        )

        api_key = get_gmaps_key()
        dir_encoded = quote(direccion + " Chile")

        # ── Links directos (siempre disponibles) ──
        col_ge, col_gm = st.columns(2)
        with col_ge:
            st.link_button(
                "🌍 Abrir en Google Earth",
                f"https://earth.google.com/web/search/{dir_encoded}",
                use_container_width=True,
            )
            st.caption("Herramienta Medir → Polígono → trace el contorno → obtenga el área en m²")
        with col_gm:
            st.link_button(
                "🗺️ Abrir en Google Maps",
                f"https://www.google.com/maps/search/{dir_encoded}",
                use_container_width=True,
            )
            st.caption("Clic derecho sobre el edificio → Medir distancia")

        st.divider()

        # ── Con API key: geocodificación automática ──
        if api_key:
            if st.button("📍 Geocodificar dirección y mostrar en mapa", key="geo_btn"):
                with st.spinner("Consultando Google Maps..."):
                    geo = geocodificar(direccion, api_key)
                if geo:
                    lat, lng, addr = geo
                    st.success(f"✅ Dirección encontrada: **{addr}**")
                    st.map(pd.DataFrame({"lat": [lat], "lon": [lng]}), zoom=17)
                    st.caption(f"Coordenadas: {lat:.6f}, {lng:.6f}")
                else:
                    st.error("No se encontró la dirección. Verifique el texto ingresado.")
        else:
            st.info(
                "**Búsqueda automática no activa** — agregue `GOOGLE_MAPS_API_KEY` "
                "en Secrets de Streamlit Cloud para activar el mapa integrado. "
                "Por ahora use los botones de arriba para abrir la dirección en Google Earth o Maps."
            )

        st.divider()
        st.markdown("**Pasos para medir en Google Earth:**")
        st.markdown(
            "1. Haga clic en el botón **Abrir en Google Earth** arriba\n"
            "2. El edificio aparecerá centrado en el mapa\n"
            "3. En el menú izquierdo, haga clic en **Medir** (ícono de regla)\n"
            "4. Seleccione **Polígono** y trace el contorno exterior del edificio\n"
            "5. Google Earth muestra el **área en m²** — ese es el área de la planta\n"
            "6. Multiplique: **área planta × (N° pisos + N° subterráneos)** = superficie total\n"
            "7. Ingrese ese valor en el campo de superficie del formulario"
        )


def widget_formulario_componente(prefix, zona, pisos, anio, aplica_iva,
                                  default_tipo="Comunidad", label_tipo="Tipo de inmueble",
                                  sup_sugerida=None, mostrar_dist=False,
                                  pct_comun=None, pct_pct=None,
                                  sup_total=None):
    """
    Formulario completo de un componente.
    Si mostrar_dist=True, muestra la tabla de distribución de superficies
    justo debajo del campo Superficie (m²).
    """
    tipos = list(SISTEMAS_POR_TIPO.keys())
    idx   = tipos.index(default_tipo) if default_tipo in tipos else 0
    tipo  = st.selectbox(label_tipo, tipos, index=idx, key=f"{prefix}_tipo")
    sis   = st.selectbox("Sistema constructivo", SISTEMAS_POR_TIPO[tipo], key=f"{prefix}_sis")
    niv   = st.selectbox("Nivel de terminaciones", NIVELES_POR_TS[(tipo, sis)],
                         key=f"{prefix}_niv",
                         help="Básico = sin lujos · Medio = estándar · Alto = premium")

    # ── Tabla referencia VUB (antes del campo VUB) ──
    if zona:
        vub = widget_vub(prefix, zona, tipo, sis, niv)
    else:
        vub = st.number_input("VUB — Valor Unitario Base (UF/m²)", min_value=1.0,
                              max_value=200.0, value=None, step=0.5, format="%.1f",
                              key=f"{prefix}_vub")

    # ── Campo Superficie (m²) ──
    ph_sup = f"Estimado: {sup_sugerida:,.0f} m²" if sup_sugerida else "Ej: 3500"
    sup = st.number_input(
        "Superficie (m²)", min_value=1, max_value=500_000,
        value=sup_sugerida if sup_sugerida else None,
        placeholder=ph_sup, key=f"{prefix}_sup",
    )

    # ── Tabla de distribución de superficies (debajo de Superficie, si aplica) ──
    if mostrar_dist and sup_total and pct_comun is not None and pct_pct is not None:
        sup_comun_ref = round(sup_total * pct_comun)
        sup_units_ref = sup_total - sup_comun_ref
        dist_html = f"""
<div style="margin:8px 0 12px 0;padding:10px 14px;background:#f8faff;
            border-left:4px solid #1f77b4;border-radius:0 6px 6px 0;font-size:13px">
  <div style="font-weight:600;margin-bottom:6px;color:#1d3557">
    📐 Distribución de superficies aplicada ({pct_pct}% bienes comunes / {100-pct_pct}% unidades)
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px">
    <div style="text-align:center">
      <div style="font-size:11px;color:#666">Superficie total</div>
      <div style="font-size:16px;font-weight:600">{sup_total:,.0f} m²</div>
    </div>
    <div style="text-align:center">
      <div style="font-size:11px;color:#1d4ed8">Bienes comunes ({pct_pct}%)</div>
      <div style="font-size:16px;font-weight:600;color:#1d4ed8">{sup_comun_ref:,.0f} m²</div>
    </div>
    <div style="text-align:center">
      <div style="font-size:11px;color:#92400e">Unidades privadas ({100-pct_pct}%)</div>
      <div style="font-size:16px;font-weight:600;color:#92400e">{sup_units_ref:,.0f} m²</div>
    </div>
  </div>
  <div style="font-size:11px;color:#888;margin-top:6px">
    ⚠️ Estimación referencial. Use el Reglamento de Copropiedad o planos del edificio para el valor exacto.
  </div>
</div>
"""
        st.markdown(dist_html, unsafe_allow_html=True)

    # ── Monto asegurado ──
    monto = st.number_input("Monto asegurado en póliza (UF)", min_value=0,
                            value=None, placeholder="0", key=f"{prefix}_monto",
                            help="Ingrese 0 si no hay seguro contratado para este componente.")

    return {"tipo":tipo,"sis":sis,"niv":niv,"vub":vub,"sup":sup,"monto":monto,
            "zona":zona,"pisos":pisos,"anio":anio,"aplica_iva":aplica_iva}


def validar_comp(d, campo):
    errs = []
    if not d.get("vub"):       errs.append(f"Ingrese el VUB (UF/m²) de {campo}.")
    if not d.get("sup"):       errs.append(f"Ingrese la superficie de {campo}.")
    if d.get("monto") is None: errs.append(f"Ingrese el monto asegurado de {campo} (puede ser 0).")
    return errs


def widget_resultado(label, res, datos, danio_pct, nota="", expanded=True):
    """Muestra resultado de un componente calculado."""
    vr    = res["vr"]
    monto = datos.get("monto") or 0
    ratio, infra = evaluar(monto, vr)
    danio_ = vr * (danio_pct / 100)
    ind_   = indemn(danio_, monto, vr)

    with st.expander(f"📦 {label} — **{vr:,.2f} UF**", expanded=expanded):
        if nota:
            st.caption(nota)
        if monto <= 0:
            st.info("ℹ️ Sin monto asegurado registrado.")
        elif infra:
            st.warning(f"⚠️ **Infrasegurado.** Cobertura: **{ratio*100:.1f}%** — Brecha: **{vr-monto:,.2f} UF**")
        else:
            st.success(f"✅ Cobertura adecuada ({ratio*100:.1f}%)")

        c1, c2, c3 = st.columns(3)
        c1.metric("Valor de reconstrucción", f"{vr:,.2f} UF")
        c2.metric("Monto asegurado", f"{monto:,.2f} UF" if monto > 0 else "No indicado")
        c3.metric("Cobertura", f"{ratio*100:.1f}%" if monto > 0 else "—",
                  delta=f"{(ratio-1)*100:.1f}%" if monto > 0 else None,
                  delta_color="normal" if not infra else "inverse")
        if monto > 0:
            st.progress(min(ratio, 1.0), text=f"Cobertura: {ratio*100:.1f}%")

        st.markdown("**Desglose del cálculo**")
        st.markdown(f"""
| # | Concepto | Valor |
|---|----------|-------|
| 1 | VUB — {datos.get('tipo','')}/{datos.get('sis','')}/{datos.get('niv','')} | **{res['vub']:.1f} UF/m²** |
| 2 | × Factor geográfico | {res['fg']:.2f} |
| 3 | × Factor normativo (año {datos.get('anio','')}) | {res['fn']:.2f} |
| 4 | × Factor altura ({datos.get('pisos','')} pisos) | {res['fa']:.2f} |
| 5 | **Costo directo** ({(datos.get('sup') or 0):,.0f} m²) | **{res['cd']:,.2f} UF** |
| 6a | + Diseño del proyecto (3%) | {res['ind_det']['Diseño del proyecto']:,.2f} UF |
| 6b | + Gastos generales de obra (6%) | {res['ind_det']['Gastos generales de obra']:,.2f} UF |
| 6c | + Utilidad del contratista (12%) | {res['ind_det']['Utilidad del contratista']:,.2f} UF |
| 6d | + Imprevistos (10%) | {res['ind_det']['Imprevistos']:,.2f} UF |
| 7 | **Subtotal sin IVA** | **{res['st']:,.2f} UF** |
| 8 | + IVA 19% | {res['iv']:,.2f} UF |
| ✓ | **VALOR DE RECONSTRUCCIÓN** | **{vr:,.2f} UF** |
""")
        st.markdown(f"**Simulación — daño del {danio_pct}%**")
        s1, s2, s3 = st.columns(3)
        s1.metric("Daño estimado", f"{danio_:,.2f} UF")
        s2.metric("Indemnización real", f"{ind_:,.2f} UF" if monto > 0 else "—")
        if infra:
            s3.metric("Pérdida no cubierta", f"{danio_-ind_:,.2f} UF", delta_color="inverse")
            st.warning(f"**Art. 553 CCom:** recibiría **{ind_:,.2f} UF** en vez de **{danio_:,.2f} UF**. "
                       f"Pérdida: **{danio_-ind_:,.2f} UF**.")


# ─────────────────────────────────────────────────────────
# INFORME TXT
# ─────────────────────────────────────────────────────────
def _bloque_txt(etiq, res, datos, danio_pct):
    monto = datos.get("monto") or 0
    vr    = res["vr"]
    ratio, infra = evaluar(monto, vr)
    d = vr * (danio_pct / 100)
    i = indemn(d, monto, vr)
    lns = [
        f"  [{etiq}]",
        f"    Tipo/Sistema/Nivel  : {datos.get('tipo','')}/{datos.get('sis','')}/{datos.get('niv','')}",
        f"    VUB ingresado       : {res['vub']:.1f} UF/m²",
        f"    Superficie          : {datos.get('sup',0):,.0f} m²",
        f"    Factores            : geográfico {res['fg']:.2f} · normativo {res['fn']:.2f} · altura {res['fa']:.2f}",
        f"    Costo directo       : {res['cd']:>12,.2f} UF",
        f"    Costos ind. (31%)   : {res['ci']:>12,.2f} UF",
        f"    Subtotal s/IVA      : {res['st']:>12,.2f} UF",
        (f"    IVA 19%             : {res['iv']:>12,.2f} UF" if res["aplica_iva"] else
         f"    IVA 19%             :       no aplica"),
        f"    VALOR RECONSTRUCCIÓN: {vr:>12,.2f} UF",
        "",
        (f"    Monto asegurado     : {monto:>12,.2f} UF" if monto > 0 else
         f"    Monto asegurado     :    No indicado"),
        (f"    Cobertura           : {ratio*100:>11.1f} %" if monto > 0 else
         f"    Cobertura           :            —"),
        f"    Infraseguro         : {'SÍ ⚠' if infra else 'NO ✓'}",
    ]
    if infra:
        lns.append(f"    Brecha sin cubrir   : {vr-monto:>12,.2f} UF")
    lns += [
        f"    Simulación ({danio_pct:.0f}% daño)",
        f"      Daño estimado     : {d:>12,.2f} UF",
        (f"      Indemnización     : {i:>12,.2f} UF" if monto > 0 else
         f"      Indemnización     :    Ver VR"),
    ]
    if infra:
        lns.append(f"      Pérdida           : {d-i:>12,.2f} UF")
    return "\n".join(lns)


def generar_informe(caso):
    sep  = "=" * 64
    sep2 = "─" * 64
    hoy  = date.today().strftime("%d/%m/%Y")
    lns  = [
        "INFORME DE VALOR DE RECONSTRUCCIÓN",
        "Conforme DFL 251, DS 1055, CCom art. 553 y Ley 21.442",
        sep,
        f"  Nombre / Referencia : {caso['nombre']}",
        f"  Dirección           : {caso['direccion']}",
        f"  Zona geográfica     : {caso.get('zona','—')}",
        f"  Número de pisos     : {caso.get('pisos','—')}",
        f"  Año de construcción : {caso.get('anio','—')}",
        f"  Fecha de cálculo    : {hoy}",
        sep, "",
    ]
    modo = caso["modo"]
    if modo == "simple":
        lns += ["INMUEBLE COMPLETO\n",
                _bloque_txt("Inmueble completo", caso["comp"]["res"], caso["comp"], caso["danio_pct"])]
    elif modo == "comunes":
        lns += ["BIENES Y ESPACIOS COMUNES (Ley 21.442 art. 43)\n",
                _bloque_txt("Bienes comunes", caso["comp"]["res"], caso["comp"], caso["danio_pct"])]
    elif modo == "comunidad":
        if caso.get("desglose"):
            dg = caso["desglose"]
            lns += [
                "DISTRIBUCIÓN DE SUPERFICIES",
                f"  Superficie total        : {dg['sup_total']:,.0f} m²",
                f"  % bienes comunes        : {dg['pct_pct']}%",
                f"  Superficie bienes comunes: {dg['sup_comun']:,.0f} m²",
                f"  Superficie unidades     : {dg['sup_units']:,.0f} m²",
                f"  Referencia              : Tabla Ley 21.442 / OGUC / mercado 2025",
                "",
            ]
        lns += ["PÓLIZA COLECTIVA — NCG 556 CMF", "",
                "BLOQUE 1: BIENES Y ESPACIOS COMUNES (asegurado: la comunidad)\n",
                _bloque_txt("Bienes comunes", caso["comp_comun"]["res"],
                            caso["comp_comun"], caso["danio_pct"]),
                "", sep2, "",
                "BLOQUE 2: UNIDADES PRIVADAS (asegurado: cada copropietario)\n"]
        for u in caso["unidades"]:
            lns += [_bloque_txt(u.get("nombre") or "Unidad", u["res"], u, caso["danio_pct"]), ""]
        vr_t = caso["total_vr"]
        m_t  = caso["total_monto"]
        r_t, i_t = evaluar(m_t, vr_t)
        d_t  = vr_t * (caso["danio_pct"] / 100)
        ind_t = indemn(d_t, m_t, vr_t)
        lns += [sep2, "CONSOLIDADO TOTAL",
                f"  VR bienes comunes  : {caso['vr_comun']:>12,.2f} UF",
                f"  VR unidades        : {caso['vr_units']:>12,.2f} UF",
                f"  VR TOTAL           : {vr_t:>12,.2f} UF",
                (f"  Monto asegurado    : {m_t:>12,.2f} UF" if m_t > 0 else
                 f"  Monto asegurado    :    No indicado"),
                f"  Infraseguro global : {'SÍ ⚠' if i_t else 'NO ✓'}"]
        if m_t > 0:
            lns += [f"  Indemnización ({caso['danio_pct']:.0f}%): {ind_t:>12,.2f} UF"]
        if i_t:
            lns.append(f"  Pérdida            : {d_t-ind_t:>12,.2f} UF")
    lns += ["", sep2,
            "Nota: Informe referencial. Verificar con tasador habilitado y póliza vigente.",
            "VUB: ingresado por el usuario. Tabla MINVU: minvu.gob.cl",
            "Normativa: DFL 251 · DS 1055 · CCom 553 · Ley 21.442 · NCG 556 CMF"]
    return "\n".join(lns)


# ─────────────────────────────────────────────────────────
# CONFIGURACIÓN PÁGINA
# ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Seguro de Reconstrucción — Chile",
    page_icon="🏢", layout="centered",
    initial_sidebar_state="collapsed",
)
st.markdown("""
<style>
.stApp { max-width: 820px; margin: auto; }
.block-container { padding-top: 2rem; padding-bottom: 3rem; }
div[data-testid="stMetricValue"] { font-size: 1.3rem; }
h1 { font-size: 1.6rem !important; }
h2 { font-size: 1.2rem !important; }
</style>
""", unsafe_allow_html=True)

st.title("🏢 Calculadora de Valor de Reconstrucción")
st.caption("Seguros de inmuebles en Chile · DFL 251 · DS 1055 · CCom art. 553 · Ley 21.442 · NCG 556 CMF")

tab_calc, tab_casos, tab_como = st.tabs(["📐 Calcular", "📋 Mis casos", "ℹ️ Marco normativo"])

# ══════════════════════════════════════════════════════════
# PESTAÑA: CALCULAR
# ══════════════════════════════════════════════════════════
with tab_calc:

    # ── Identificación ──
    st.subheader("Identificación de la propiedad")
    col_n, col_d = st.columns(2)
    with col_n:
        nombre    = st.text_input("Nombre o referencia", placeholder="Ej: Edificio Torres del Parque")
    with col_d:
        direccion = st.text_input("Dirección completa", placeholder="Calle, número, comuna, región")

    # Herramienta de dirección (siempre visible si hay texto)
    widget_herramienta_direccion(direccion)

    # ── Datos generales ──
    st.subheader("Datos generales del inmueble")
    g1, g2, g3, g4 = st.columns(4)
    with g1:
        zona = st.selectbox("Zona geográfica", [""] + list(FACTOR_GEOGRAFICO.keys()),
                            format_func=lambda x: "Seleccionar..." if x == "" else x)
    with g2:
        pisos = st.number_input("N° de pisos", min_value=1, max_value=100,
                                value=None, placeholder="Ej: 12")
    with g3:
        anio = st.number_input("Año construcción", min_value=1900, max_value=2025,
                               value=None, placeholder="Ej: 2005")
    with g4:
        aplica_iva = st.checkbox("IVA (19%)", value=True)

    danio_pct = st.slider("% de daño a simular en siniestro", 1, 100, 50,
                          help="Porcentaje del inmueble dañado en el siniestro hipotético.")

    datos_ok = bool(zona and pisos and anio)
    if zona and datos_ok:
        widget_tabla_refs_vub(zona)

    # ── Modo de cálculo ──
    st.subheader("¿Qué desea calcular?")
    modo = st.radio("Seleccione el alcance:", [
        "🏠  Inmueble completo — casas, locales o edificio en bloque",
        "🏛️  Solo bienes y espacios comunes — póliza de la comunidad (Ley 21.442 art. 43)",
        "🏢  Comunidad completa — bienes comunes + unidades privadas (NCG 556 CMF)",
    ])
    modo_key = ("simple" if "completo" in modo
                else "comunes" if "Solo bienes" in modo
                else "comunidad")
    st.divider()

    # ════════════════════════
    # MODO 1: INMUEBLE COMPLETO
    # ════════════════════════
    if modo_key == "simple":
        st.markdown("#### Datos del inmueble")
        if not datos_ok:
            st.info("Complete primero zona, pisos y año de construcción.")
            d = None
        else:
            d = widget_formulario_componente("s", zona, pisos, anio, aplica_iva,
                                             default_tipo="Edificio")

        if st.button("Calcular", type="primary", use_container_width=True, key="btn_s"):
            errs = [] if datos_ok else ["Complete zona, pisos y año."]
            if d: errs += validar_comp(d, "el inmueble")
            for e in errs: st.error(f"⚠️ {e}")
            if not errs:
                res = calcular_vr(d["vub"], d["sup"], zona, pisos, anio, aplica_iva)
                widget_resultado("Inmueble completo", res,
                                 {**d, "zona":zona,"pisos":pisos,"anio":anio}, danio_pct)
                caso = dict(nombre=nombre or "Sin nombre", direccion=direccion or "—",
                            zona=zona, pisos=pisos, anio=anio, danio_pct=danio_pct,
                            modo="simple",
                            comp={**d,"res":res,"zona":zona,"pisos":pisos,"anio":anio},
                            total_vr=res["vr"], total_monto=d["monto"] or 0)
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("💾 Guardar", use_container_width=True, key="g_s"):
                        st.session_state.setdefault("casos", []).append(caso)
                        st.success("Caso guardado en 'Mis casos'.")
                with b2:
                    st.download_button("📄 Descargar informe",
                                       data=generar_informe(caso).encode(),
                                       file_name=f"informe_{(nombre or 'inmueble').replace(' ','_').lower()}.txt",
                                       mime="text/plain", use_container_width=True, key="dl_s")

    # ════════════════════════
    # MODO 2: SOLO BIENES COMUNES
    # ════════════════════════
    elif modo_key == "comunes":
        st.markdown("#### Bienes y espacios comunes")
        st.info("**Ley 21.442, art. 43** — Seguro obligatorio de la comunidad, "
                "independiente del seguro de cada unidad privada.")
        st.caption("Incluye: estructura, fachadas, instalaciones centrales, ascensores, "
                   "subterráneos, piscina, áreas verdes, pasillos y estacionamientos comunes.")
        if not datos_ok:
            st.info("Complete primero zona, pisos y año.")
            d = None
        else:
            d = widget_formulario_componente("bc", zona, pisos, anio, aplica_iva,
                                             default_tipo="Comunidad",
                                             label_tipo="Tipo (bienes comunes)")

        if st.button("Calcular bienes comunes", type="primary",
                     use_container_width=True, key="btn_bc"):
            errs = [] if datos_ok else ["Complete zona, pisos y año."]
            if d: errs += validar_comp(d, "bienes comunes")
            for e in errs: st.error(f"⚠️ {e}")
            if not errs:
                res = calcular_vr(d["vub"], d["sup"], zona, pisos, anio, aplica_iva)
                widget_resultado("Bienes y espacios comunes", res,
                                 {**d,"zona":zona,"pisos":pisos,"anio":anio}, danio_pct,
                                 nota="Asegurado: la comunidad (Ley 21.442 art. 43 — OBLIGATORIO)")
                caso = dict(nombre=nombre or "Sin nombre", direccion=direccion or "—",
                            zona=zona, pisos=pisos, anio=anio, danio_pct=danio_pct,
                            modo="comunes",
                            comp={**d,"res":res,"zona":zona,"pisos":pisos,"anio":anio},
                            total_vr=res["vr"], total_monto=d["monto"] or 0)
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("💾 Guardar", use_container_width=True, key="g_bc"):
                        st.session_state.setdefault("casos", []).append(caso)
                        st.success("Guardado.")
                with b2:
                    st.download_button("📄 Descargar informe",
                                       data=generar_informe(caso).encode(),
                                       file_name=f"informe_{(nombre or 'comunes').replace(' ','_').lower()}.txt",
                                       mime="text/plain", use_container_width=True, key="dl_bc")

    # ════════════════════════
    # MODO 3: COMUNIDAD COMPLETA
    # ════════════════════════
    else:
        st.info(
            "**NCG 556 CMF (dic. 2025)** — La póliza colectiva se estructura en dos bloques separados: "
            "**Bloque 1** bienes comunes (asegurado: la comunidad) · "
            "**Bloque 2** unidades privadas (asegurado: cada copropietario)."
        )

        # ── Superficie total ──
        st.markdown("---")
        sup_total = st.number_input(
            "Superficie total del edificio (m²)",
            min_value=1, max_value=2_000_000, value=None, placeholder="Ej: 12000",
            help="Suma de TODOS los pisos + subterráneos. Use la herramienta de dirección para medirla.",
            key="sup_total_edificio",
        )

        # ── Panel de distribución (debajo de Superficie total) ──
        pct_comun, sup_comun_calc, sup_units_calc = widget_distribucion_superficies(sup_total)

        # ── Bloque 1: Bienes comunes ──
        st.markdown("---")
        st.markdown("#### Bloque 1 — Bienes y espacios comunes")
        st.caption("Estructura, fachadas, instalaciones centrales, ascensores, "
                   "subterráneos y toda área de dominio común.")
        if datos_ok:
            d_comun = widget_formulario_componente(
                "c_bc", zona, pisos, anio, aplica_iva,
                default_tipo="Comunidad", label_tipo="Tipo (bienes comunes)",
                sup_sugerida=sup_comun_calc,
                mostrar_dist=True,
                pct_comun=pct_comun,
                pct_pct=int(pct_comun * 100),
                sup_total=sup_total,
            )
        else:
            st.info("Complete zona, pisos y año de construcción.")
            d_comun = None

        # ── Bloque 2: Unidades privadas ──
        st.markdown("---")
        st.markdown("#### Bloque 2 — Unidades privadas")
        st.caption("VUB con tipo **Depto** — valor de la unidad habitable sin incluir áreas comunes.")

        incluir_uni = st.checkbox(
            "Incluir unidades privadas en este análisis", value=True,
            help="Desmarque si las unidades tienen seguros individuales separados.",
        )
        datos_uni = []

        if incluir_uni and datos_ok:
            if "n_uni" not in st.session_state:
                st.session_state.n_uni = 1
            ca, cr = st.columns(2)
            with ca:
                if st.button("➕ Agregar unidad", use_container_width=True):
                    st.session_state.n_uni += 1
            with cr:
                if st.button("➖ Quitar última", use_container_width=True,
                             disabled=st.session_state.n_uni <= 1):
                    st.session_state.n_uni -= 1

            # Sugerencia de superficie por unidad
            sup_uni_sug = None
            if sup_units_calc and st.session_state.n_uni > 0:
                sup_uni_sug = round(sup_units_calc / st.session_state.n_uni)
                st.caption(
                    f"💡 Superficie promedio sugerida por unidad: **{sup_uni_sug:,.0f} m²** "
                    f"({sup_units_calc:,.0f} m² ÷ {st.session_state.n_uni} unidades)"
                )

            for i in range(st.session_state.n_uni):
                with st.expander(f"Unidad privada {i+1}", expanded=(i == 0)):
                    nom_u = st.text_input("Identificación", key=f"u_{i}_nom",
                                          placeholder="Ej: Depto 501, Local 2")
                    du = widget_formulario_componente(
                        f"u_{i}", zona, pisos, anio, aplica_iva,
                        default_tipo="Depto", label_tipo="Tipo de unidad",
                        sup_sugerida=sup_uni_sug,
                        mostrar_dist=True,
                        pct_comun=pct_comun,
                        pct_pct=int(pct_comun * 100),
                        sup_total=sup_total,
                    )
                    du["nombre"] = nom_u
                    du["poliza_propia"] = st.checkbox(
                        "Tiene póliza propia vigente (hipotecaria u otra)",
                        key=f"u_{i}_prop",
                        help="Puede renunciar a cobertura en póliza colectiva (art. 43 b), "
                             "pero igual contribuye al pago de bienes comunes.",
                    )
                    datos_uni.append(du)

        elif incluir_uni and not datos_ok:
            st.info("Complete los datos generales para habilitar las unidades.")

        st.divider()
        if st.button("Calcular comunidad completa", type="primary",
                     use_container_width=True, key="btn_com"):
            errs = [] if datos_ok else ["Complete zona, pisos y año."]
            if d_comun:
                errs += validar_comp(d_comun, "bienes comunes")
            else:
                errs += ["Complete los datos de bienes comunes."]
            if incluir_uni:
                for i, du in enumerate(datos_uni, 1):
                    errs += validar_comp(du, f"unidad {i}")
            for e in errs:
                st.error(f"⚠️ {e}")

            if not errs:
                res_c = calcular_vr(d_comun["vub"], d_comun["sup"], zona, pisos, anio, aplica_iva)
                comp_c = {**d_comun, "res":res_c, "zona":zona, "pisos":pisos, "anio":anio}

                units_calc = []
                for du in datos_uni:
                    r_u = calcular_vr(du["vub"], du["sup"], zona, pisos, anio, aplica_iva)
                    units_calc.append({**du, "res":r_u, "zona":zona, "pisos":pisos, "anio":anio})

                vr_c   = res_c["vr"]
                vr_u   = sum(u["res"]["vr"] for u in units_calc)
                vr_t   = vr_c + vr_u
                m_c    = d_comun["monto"] or 0
                m_u    = sum(u.get("monto") or 0 for u in datos_uni)
                m_t    = m_c + m_u
                r_t, i_t = evaluar(m_t, vr_t)
                d_t    = vr_t * (danio_pct / 100)
                ind_t  = indemn(d_t, m_t, vr_t)

                st.divider()
                st.subheader("Resultados")

                # Resumen consolidado
                st.markdown("##### Resumen consolidado")
                if m_t <= 0:
                    st.info("ℹ️ Sin monto asegurado. El valor calculado indica cuánto debería asegurarse.")
                elif i_t:
                    st.warning(f"⚠️ **Infraseguro global.** Cobertura: **{r_t*100:.1f}%** "
                               f"— Brecha: **{vr_t-m_t:,.2f} UF**")
                else:
                    st.success(f"✅ Cobertura global adecuada ({r_t*100:.1f}%)")

                t1, t2, t3, t4 = st.columns(4)
                t1.metric("VR total comunidad", f"{vr_t:,.2f} UF")
                t2.metric("Bienes comunes",     f"{vr_c:,.2f} UF")
                t3.metric("Unidades privadas",  f"{vr_u:,.2f} UF")
                t4.metric("Cobertura global",
                          f"{r_t*100:.1f}%" if m_t > 0 else "—",
                          delta=f"{(r_t-1)*100:.1f}%" if m_t > 0 else None,
                          delta_color="normal" if not i_t else "inverse")
                if m_t > 0:
                    st.progress(min(r_t, 1.0), text=f"Cobertura global: {r_t*100:.1f}%")

                with st.expander(f"🔥 Simulación total — daño del {danio_pct}%"):
                    sc1, sc2, sc3 = st.columns(3)
                    sc1.metric("Daño total", f"{d_t:,.2f} UF")
                    sc2.metric("Indemnización global",
                               f"{ind_t:,.2f} UF" if m_t > 0 else "—")
                    if i_t and m_t > 0:
                        sc3.metric("Pérdida no cubierta",
                                   f"{d_t-ind_t:,.2f} UF", delta_color="inverse")

                # Tabla comparativa
                st.markdown("---")
                st.markdown("##### Tabla comparativa por componente")
                filas = []
                r_c2, i_c2 = evaluar(m_c, vr_c)
                filas.append({
                    "Componente":"Bienes comunes","Asegurado":"Comunidad",
                    "Sup. m²":f"{d_comun['sup']:,.0f}","VUB":f"{d_comun['vub']:.1f}",
                    "VR (UF)":f"{vr_c:,.2f}",
                    "Asegurado (UF)":f"{m_c:,.2f}" if m_c > 0 else "—",
                    "Cobertura":f"{r_c2*100:.1f}%" if m_c > 0 else "—",
                    "Estado":"⚠️" if i_c2 else ("✅" if m_c > 0 else "ℹ️"),
                })
                for u in units_calc:
                    vr_u2 = u["res"]["vr"]
                    m_u2  = u.get("monto") or 0
                    r_u2, i_u2 = evaluar(m_u2, vr_u2)
                    pp = " (póliza propia)" if u.get("poliza_propia") else ""
                    filas.append({
                        "Componente": u.get("nombre") or "Unidad",
                        "Asegurado": f"Copropietario{pp}",
                        "Sup. m²": f"{u['sup']:,.0f}", "VUB": f"{u['vub']:.1f}",
                        "VR (UF)": f"{vr_u2:,.2f}",
                        "Asegurado (UF)": f"{m_u2:,.2f}" if m_u2 > 0 else "—",
                        "Cobertura": f"{r_u2*100:.1f}%" if m_u2 > 0 else "—",
                        "Estado": "⚠️" if i_u2 else ("✅" if m_u2 > 0 else "ℹ️"),
                    })
                filas.append({
                    "Componente":"TOTAL","Asegurado":"—",
                    "Sup. m²": f"{(d_comun['sup'] or 0)+sum(u.get('sup') or 0 for u in datos_uni):,.0f}",
                    "VUB":"—","VR (UF)":f"{vr_t:,.2f}",
                    "Asegurado (UF)":f"{m_t:,.2f}" if m_t > 0 else "—",
                    "Cobertura":f"{r_t*100:.1f}%" if m_t > 0 else "—",
                    "Estado":"⚠️" if i_t else ("✅" if m_t > 0 else "ℹ️"),
                })
                st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

                # Detalle por componente
                st.markdown("---")
                st.markdown("##### Detalle por componente")
                widget_resultado("Bienes y espacios comunes", res_c, comp_c, danio_pct,
                                 nota="Asegurado: la comunidad (Ley 21.442 art. 43 — OBLIGATORIO)",
                                 expanded=True)
                for i, u in enumerate(units_calc, 1):
                    lbl = u.get("nombre") or f"Unidad {i}"
                    nota_u = ("Póliza propia — puede renunciar a cobertura colectiva"
                              if u.get("poliza_propia")
                              else "Asegurado: copropietario (NCG 556 Bloque 2)")
                    widget_resultado(lbl, u["res"], u, danio_pct,
                                     nota=nota_u, expanded=(i == 1))

                # Guardar / Exportar
                pct_pct_val = int(pct_comun * 100)
                caso = dict(
                    nombre=nombre or "Sin nombre", direccion=direccion or "—",
                    zona=zona, pisos=pisos, anio=anio, danio_pct=danio_pct,
                    modo="comunidad",
                    comp_comun=comp_c,
                    unidades=[{**u, "nombre": u.get("nombre") or f"Unidad {j+1}"}
                               for j, u in enumerate(units_calc)],
                    vr_comun=vr_c, vr_units=vr_u, total_vr=vr_t, total_monto=m_t,
                    desglose={
                        "sup_total": sup_total, "pct_pct": pct_pct_val,
                        "sup_comun": sup_comun_calc, "sup_units": sup_units_calc,
                    } if sup_total else None,
                )
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("💾 Guardar", use_container_width=True, key="g_com"):
                        st.session_state.setdefault("casos", []).append(caso)
                        st.success("Guardado en 'Mis casos'.")
                with b2:
                    st.download_button(
                        "📄 Descargar informe",
                        data=generar_informe(caso).encode(),
                        file_name=f"informe_{(nombre or 'comunidad').replace(' ','_').lower()}.txt",
                        mime="text/plain", use_container_width=True, key="dl_com",
                    )

# ══════════════════════════════════════════════════════════
# PESTAÑA: MIS CASOS
# ══════════════════════════════════════════════════════════
with tab_casos:
    casos = st.session_state.get("casos", [])
    if not casos:
        st.info("Aún no tiene casos guardados.")
    else:
        st.caption(f"{len(casos)} caso{'s' if len(casos) > 1 else ''} guardado{'s' if len(casos) > 1 else ''}")
        modos_lbl = {"simple":"Completo","comunes":"Bienes comunes","comunidad":"Comunidad"}
        for i, c in enumerate(casos):
            vr_c = c["total_vr"]
            m_c  = c["total_monto"]
            r_c, inf_c = evaluar(m_c, vr_c)
            estado = "⚠️ Infraseguro" if inf_c else ("✅ Cubierto" if m_c > 0 else "ℹ️ Sin seguro")
            with st.expander(
                f"{estado}  |  {c['nombre']}  —  {vr_c:,.2f} UF  [{modos_lbl.get(c['modo'],'—')}]"
            ):
                cc1, cc2, cc3 = st.columns(3)
                cc1.metric("Valor de reconstrucción", f"{vr_c:,.2f} UF")
                cc2.metric("Monto asegurado", f"{m_c:,.2f} UF" if m_c > 0 else "No indicado")
                cc3.metric("Cobertura", f"{r_c*100:.1f}%" if m_c > 0 else "—")
                st.caption(f"{c.get('zona','—')} · {c.get('pisos','—')} pisos · año {c.get('anio','—')}")
                st.download_button(
                    "📄 Descargar informe",
                    data=generar_informe(c).encode(),
                    file_name=f"informe_{c['nombre'].replace(' ','_').lower()}.txt",
                    mime="text/plain", key=f"dl_caso_{i}",
                )
        if st.button("🗑️ Limpiar todos los casos"):
            st.session_state.casos = []
            st.rerun()

# ══════════════════════════════════════════════════════════
# PESTAÑA: MARCO NORMATIVO
# ══════════════════════════════════════════════════════════
with tab_como:
    st.subheader("¿Qué es el valor de reconstrucción?")
    st.markdown("""
Es el costo real de volver a construir la propiedad **desde cero**.
Es el monto que debe quedar cubierto en la póliza. Si la póliza cubre menos, hay **infraseguro**
y la compañía pagará solo en proporción a la prima pagada.
""")

    st.subheader("Distribución de superficies: bienes comunes vs unidades")
    st.markdown("""
| Fuente | Referencia | Uso |
|--------|------------|-----|
| **Ley 21.442 / Edifito** | Bienes comunes = **50–70% del VR total** | Valor asegurado |
| **ComunidadFeliz** | Bienes comunes = **60–80% del monto asegurado** | Monto póliza |
| **OGUC art. 5.1.11** | Superficie común < **20% sup. útil** no cuenta para constructibilidad | Permisos |
| **Práctica de mercado** | Superficie física común ≈ **30–60% sup. total** según amenidades | Estimación |
| **Reglamento de Copropiedad** | Porcentaje inscrito en Conservador de Bienes Raíces | **Valor legal vinculante** |
""")

    st.subheader("Marco normativo")
    with st.expander("Ley 21.442 — art. 43 (Seguro obligatorio comunidad)"):
        st.markdown("""
Todo condominio habitacional debe contratar seguro colectivo contra incendio cubriendo:
- **Obligatoriamente:** bienes e instalaciones comunes.
- **Opcionalmente:** unidades privadas (el copropietario puede renunciar si tiene póliza propia).
- El copropietario **nunca puede eximirse** del pago por bienes comunes.
""")
    with st.expander("NCG 556 CMF — dic. 2025 (Estructura de la póliza)"):
        st.markdown("""
| Bloque | Cubre | Asegurado | Carácter |
|--------|-------|-----------|----------|
| **1 — Bienes comunes** | Estructura, instalaciones, áreas comunes | La comunidad | Obligatorio |
| **2 — Unidades privadas** | Cada depto, local, bodega | El copropietario | Opcional colectivo |

Ante daños parciales en una unidad, la indemnización se destina **primero a reparación**, no al crédito hipotecario.
""")
    with st.expander("CCom Art. 553 — Regla proporcional"):
        st.markdown("""
Si el monto asegurado < valor real → la compañía paga solo en proporción a la prima.

> Si asegura el **70%** del valor real → recibirá solo el **70%** del daño, aunque el siniestro sea parcial.

**Por eso es fundamental calcular y asegurar el valor correcto.**
""")
    with st.expander("Pasos del cálculo de VR"):
        st.markdown("""
| Paso | Concepto |
|------|----------|
| 1 | VUB (UF/m²) ingresado por el usuario |
| 2 | × Factor geográfico: Metropolitana 1.05 / Intermedia 1.00 / Aislada 1.15 |
| 3 | × Factor normativo: <1985→1.15 / 1985-2000→1.10 / 2001-2010→1.05 / >2010→1.00 |
| 4 | × Factor altura: 1-2p→1.00 / 3-5p→1.05 / 6-10p→1.10 / 11+→1.15 |
| 5 | = Costo directo |
| 6 | + Indirectos 31%: diseño 3% + GG 6% + utilidad 12% + imprevistos 10% |
| 7 | + IVA 19% (si corresponde) |
| ✓ | = Valor de Reconstrucción |
""")
    with st.expander("Fuentes del VUB"):
        st.markdown("""
- **Tabla MINVU** (oficial, en pesos, trimestral): [minvu.gob.cl](https://www.minvu.gob.cl/elementos-tecnicos/tabla-de-costos-unitarios/)
- **Tasador habilitado** — el más preciso para cada caso específico
- **Corredor de seguros** — usa tablas validadas por la compañía aseguradora
- **Referencias de mercado** (orientativas): incluidas en la app al seleccionar zona, tipo y nivel
""")

    st.divider()
    st.caption("Programa referencial. No reemplaza tasación profesional ni asesoría de corredor certificado.")
