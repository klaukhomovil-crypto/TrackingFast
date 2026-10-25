import re
import time
import subprocess
import sys
import pandas as pd
import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright

st.set_page_config(
    page_title="LATAM Tracker", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- ESTILOS CSS PARA ADAPTAR A PANTALLAS MÓVILES Y ELIMINAR SCROLL INNECESARIO ---
st.markdown("""
    <style>
        /* Reducir márgenes superiores e inferiores en la versión móvil */
        .block-container {
            padding-top: 1.5rem !important;
            padding-bottom: 1rem !important;
            padding-left: 0.8rem !important;
            padding-right: 0.8rem !important;
        }
        /* Ajustar tamaño de títulos para que no ocupen media pantalla */
        h1 { font-size: 1.5rem !important; margin-bottom: 0.2rem !important; }
        h3, .stSubheader { font-size: 1.1rem !important; }
        /* Botones más compactos */
        .stButton>button {
            width: 100%;
            border-radius: 8px;
            padding-top: 0.4rem;
            padding-bottom: 0.4rem;
        }
        /* Ocultar pie de página de Streamlit para ganar espacio vertical */
        footer {visibility: hidden;}
        #MainMenu {visibility: hidden;}
    </style>
""", unsafe_allow_innerHTML=True)

# --- INSTALACIÓN AUTOMÁTICA DE PLAYWRIGHT PARA STREAMLIT CLOUD ---
@st.cache_resource
def instalar_playwright():
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    except Exception as e:
        print(f"Error instalando navegador: {e}")

instalar_playwright()

st.title("📦 Monitoreo LATAM Cargo")

if "guias_db" not in st.session_state:
    st.session_state.guias_db = {}

if "input_guia" not in st.session_state:
    st.session_state.input_guia = ""

# --- FASE 1: INGRESO DE GUÍA ---
col1, col2 = st.columns([2, 1])
with col1:
    numero_guia = st.text_input(
        "Ingrese Guía:", 
        value=st.session_state.input_guia, 
        placeholder="XXX-XXXXXXXX",
        key="widget_guia"
    )

with col2:
    st.write(" ")
    st.write(" ")
    boton_agregar = st.button("➕ Agregar")

patron_guia = r"^\d{3}-\d{8}$"

if boton_agregar:
    guia_limpia = numero_guia.strip()
    if re.match(patron_guia, guia_limpia):
        if guia_limpia not in st.session_state.guias_db:
            st.session_state.guias_db[guia_limpia] = {
                "Estado": "Pendiente",
                "Origen": "Pendiente",
                "Destino": "Pendiente",
                "Vuelos": "Pendiente",
                "ETD": "Pendiente",
                "ETA": "Pendiente",
                "Piezas": "Pendiente",
                "Última Consulta": "Sin consultar"
            }
            st.session_state.input_guia = ""
            st.success(f"Guía {guia_limpia} agregada.")
            st.rerun()
        else:
            st.warning("Esta guía ya está en la lista.")
    else:
        st.error("❌ Formato incorrecto (Ej: 045-56598360)")

# --- FUNCIÓN DE EXTRACCIÓN ---
def consultar_latam_rapido(guia):
    prefijo, correlativo = guia.split("-")
    url = "https://www.latamcargo.com/es/trackshipment"
    
    try:
        zona_horaria = ZoneInfo("America/Lima")
        hora_consulta = datetime.now(zona_horaria).strftime("%H:%M:%S")
    except:
        hora_consulta = datetime.now().strftime("%H:%M:%S")
    
    resultado = {
        "Estado": "No encontrado",
        "Origen": "N/D",
        "Destino": "N/D",
        "Vuelos": "N/D",
        "ETD": "N/D",
        "ETA": "N/D",
        "Piezas": "N/D",
        "Última Consulta": hora_consulta
    }
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--disable-images", "--disable-gpu", "--no-sandbox"])
            page = browser.new_page()
            
            page.goto(url, timeout=25000)
            page.wait_for_timeout(1500)
            
            try:
                inputs = page.locator('input')
                if inputs.count() >= 2:
                    inputs.nth(0).fill(prefijo)
                    inputs.nth(1).fill(correlativo)
            except:
                pass

            try:
                page.click('button:has-text("Buscar"), button[type="submit"]')
            except:
                page.keyboard.press("Enter")

            page.wait_for_timeout(4500)
            
            datos_tabla = page.evaluate("""() => {
                const rows = document.querySelectorAll('tr, .row, .table-row');
                const results = [];
                rows.forEach(row => {
                    const cols = row.querySelectorAll('td, th, div');
                    const texts = Array.from(cols).map(c => c.innerText.trim()).filter(t => t.length > 0);
                    if (texts.length >= 3) {
                        results.push(texts);
                    }
                });
                return results;
            }""")
            
            texto_completo = page.inner_text("body")
            
            if "Entregado" in texto_completo or "Delivered" in texto_completo:
                resultado["Estado"] = "✅ Entregado"
            elif "En tránsito" in texto_completo or "Transit" in texto_completo:
                resultado["Estado"] = "✈️ En tránsito"
            elif "Recibido" in texto_completo:
                resultado["Estado"] = "📦 Recibido"
            else:
                resultado["Estado"] = "📋 Procesado"

            for fila in datos_tabla:
                for item in fila:
                    if item in ["MIA", "LIM", "SCL", "UIO", "BOG", "EZE", "JFK", "VVI", "MDE"]:
                        if resultado["Origen"] == "N/D":
                            resultado["Origen"] = item
                        elif resultado["Destino"] == "N/D" and item != resultado["Origen"]:
                            resultado["Destino"] = item
                    
                    elif re.match(r'^[A-Z0-9]{2,3}[\-\s]?\d{3,4}$', item, re.IGNORECASE):
                        resultado["Vuelos"] = item.upper()
                        
                    elif re.search(r'\d{1,2}[\-\/][A-Za-z]{3}[\-\/]\d{4}\s\d{2}:\d{2}', item):
                        if resultado["ETD"] == "N/D":
                            resultado["ETD"] = item
                        elif resultado["ETA"] == "N/D":
                            resultado["ETA"] = item
                            
                    elif item.isdigit() and 0 < int(item) < 10000 and resultado["Piezas"] == "N/D":
                        resultado["Piezas"] = item

            if resultado["ETD"] == "N/D":
                fechas_encontradas = re.findall(r'\d{1,2}[\-\/][A-Za-z]{3}[\-\/]\d{4}\s\d{2}:\d{2}', texto_completo)
                if len(fechas_encontradas) >= 1:
                    resultado["ETD"] = fechas_encontradas[0]
                if len(fechas_encontradas) >= 2:
                    resultado["ETA"] = fechas_encontradas[1]

            browser.close()
            return resultado

    except Exception as e:
        resultado["Estado"] = f"Error: {str(e)[:30]}"
        return resultado

# --- FASE 2: PANEL DE CONTROL ---
st.divider()

col_act1, col_act2 = st.columns([1, 1])
with col_act1:
    auto_refresh = st.checkbox("🔄 Auto 1 min", value=False)
with col_act2:
    actualizar_ahora = st.button("🔄 Actualizar")

if actualizar_ahora and st.session_state.guias_db:
    with st.spinner("Consultando..."):
        for g in list(st.session_state.guias_db.keys()):
            st.session_state.guias_db[g] = consultar_latam_rapido(g)
    st.rerun()

if st.session_state.guias_db:
    df = pd.DataFrame.from_dict(st.session_state.guias_db, orient="index")
    df.index.name = "AWB"
    # Tabla adaptada con altura controlada para evitar estirar la pantalla verticalmente
    st.dataframe(df, use_container_width=True, height=200)
    
    # --- ELIMINACIÓN COMPACTA ---
    col_del1, col_del2 = st.columns([2, 1])
    with col_del1:
        guias_lista = list(st.session_state.guias_db.keys())
        guia_a_borrar = st.selectbox("Borrar Guía:", options=guias_lista, label_visibility="collapsed")
    with col_del2:
        if st.button("❌ Borrar"):
            if guia_a_borrar in st.session_state.guias_db:
                del st.session_state.guias_db[guia_a_borrar]
                st.rerun()
else:
    st.info("Agrega guías arriba para monitorear.")

if auto_refresh and st.session_state.guias_db:
    time.sleep(60)
    for g in list(st.session_state.guias_db.keys()):
        st.session_state.guias_db[g] = consultar_latam_rapido(g)
    st.rerun()
