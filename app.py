import re
import time
import subprocess
import sys
import pandas as pd
import streamlit as st
from datetime import datetime
from playwright.sync_api import sync_playwright

st.set_page_config(page_title="Rastreador LATAM Cargo - Oficial", layout="wide")

# --- INSTALACIÓN AUTOMÁTICA DE PLAYWRIGHT PARA STREAMLIT CLOUD ---
@st.cache_resource
def instalar_playwright():
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    except Exception as e:
        print(f"Error instalando navegador: {e}")

instalar_playwright()

st.title("📦 Sistema de Monitoreo de Carga Aérea - LATAM Cargo")
st.write("Monitoreo rápido en tiempo real directamente desde el portal oficial de LATAM Cargo.")

if "guias_db" not in st.session_state:
    st.session_state.guias_db = {}

# --- FASE 1: INGRESO Y VALIDACIÓN DE GUÍA ---
st.subheader("1. Ingrese Número de Guía")

col1, col2 = st.columns([3, 1])
with col1:
    numero_guia = st.text_input("Número de Guía (Formato XXX-XXXXXXXX):", value="045-56598360", placeholder="045-56598360")

with col2:
    st.write(" ")
    st.write(" ")
    boton_agregar = st.button("➕ Agregar a Monitoreo")

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
            st.success(f"Guía {guia_limpia} agregada correctamente.")
        else:
            st.warning("Esta guía ya está registrada en la lista.")
    else:
        st.error("❌ Formato incorrecto. Ejemplo válido: 045-56598360")

# --- FUNCIÓN DE EXTRACCIÓN RÁPIDA ---
def consultar_latam_rapido(guia):
    prefijo, correlativo = guia.split("-")
    url = "https://www.latamcargo.com/es/trackshipment"
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
            
            # Llenar inputs de prefijo y documento
            try:
                inputs = page.locator('input')
                if inputs.count() >= 2:
                    inputs.nth(0).fill(prefijo)
                    inputs.nth(1).fill(correlativo)
            except:
                pass

            # Ejecutar búsqueda
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
                    if (texts.length >= 4) {
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
                fila_str = " ".join(fila)
                if "MIA" in fila_str or "LIM" in fila_str or "LA-" in fila_str or "XL" in fila_str:
                    for item in fila:
                        if item in ["MIA", "LIM", "SCL", "UIO", "BOG", "EZE", "JFK"]:
                            if resultado["Origen"] == "N/D":
                                resultado["Origen"] = item
                            elif resultado["Destino"] == "N/D":
                                resultado["Destino"] = item
                        elif re.match(r'^(LA|XL|UC|4C)[\-\s]?\d{3,4}$', item, re.IGNORECASE):
                            resultado["Vuelos"] = item
                        elif re.match(r'\d{1,2}[\-\/][A-Za-z]{3}[\-\/]\d{4}', item):
                            if resultado["ETD"] == "N/D":
                                resultado["ETD"] = item
                            elif resultado["ETA"] == "N/D":
                                resultado["ETA"] = item
                        elif item.isdigit() and 0 < int(item) < 10000 and resultado["Piezas"] == "N/D":
                            resultado["Piezas"] = item

            if resultado["Origen"] == "N/D" or resultado["Vuelos"] == "N/D":
                lineas = [l.strip() for l in texto_completo.split("\n") if l.strip()]
                for i, l in enumerate(lineas):
                    if l in ["MIA", "LIM"] and resultado["Origen"] == "N/D":
                        resultado["Origen"] = l
                    elif l in ["MIA", "LIM"] and resultado["Destino"] == "N/D":
                        resultado["Destino"] = l
                    elif re.match(r'^(LA|XL|UC)[\-\s]?\d{3,4}$', l, re.IGNORECASE):
                        resultado["Vuelos"] = l
                    elif l.isdigit() and 10 <= int(l) <= 5000 and resultado["Piezas"] == "N/D":
                        resultado["Piezas"] = l

            browser.close()
            return resultado

    except Exception as e:
        resultado["Estado"] = f"Error: {str(e)[:30]}"
        return resultado

# --- FASE 2: PANEL DE MONITOREO ---
st.divider()
st.subheader("2. Panel de Control y Actualización Automática (Cada 1 min)")

auto_refresh = st.checkbox("🔄 Activar actualización automática cada 1 minuto", value=False)

if st.button("🔄 Consultar / Actualizar Ahora"):
    with st.spinner("Consulta rápida en curso..."):
        for g in list(st.session_state.guias_db.keys()):
            st.session_state.guias_db[g] = consultar_latam_rapido(g)
    st.rerun()

if st.session_state.guias_db:
    df = pd.DataFrame.from_dict(st.session_state.guias_db, orient="index")
    df.index.name = "Número de Guía (AWB)"
    st.dataframe(df, use_container_width=True)
else:
    st.info("Agrega guías arriba para comenzar el monitoreo.")

if auto_refresh and st.session_state.guias_db:
    time.sleep(60)
    for g in list(st.session_state.guias_db.keys()):
        st.session_state.guias_db[g] = consultar_latam_rapido(g)
    st.rerun()
