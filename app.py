import streamlit as st
import pandas as pd
import numpy as np
import requests
from io import BytesIO


# Diccionario de usuarios y claves (puedes expandir esto)
USERS = {
    "miguel": "123456",
    "usuario2": "supersecreta"
}

def login():
    st.title("Acceso al Dashboard")
    username = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")
    if st.button("Ingresar"):
        if username in USERS and USERS[username] == password:
            st.session_state["logged_in"] = True
            st.session_state["username"] = username
            st.success(f"¡Bienvenido, {username}!")
        else:
            st.error("Usuario o contraseña incorrectos.")

if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
    login()
    st.stop()



# --- Configuración de la página
st.set_page_config(
    page_title="Dashboard de Maquinaria",
    layout="wide",
)

# --- Cargar datos desde Google Drive (usando secrets.toml)
@st.cache_data(show_spinner=False)
def load_data_from_drive():
    url = st.secrets["drive_url"]
    response = requests.get(url)
    if response.status_code == 200:
        xls = pd.ExcelFile(BytesIO(response.content))
        df_ops = xls.parse("BASE DE DATOS")
        df_maint = xls.parse("MANTENIMIENTOS")
        df_faenas = xls.parse("FAENAS")
        df_ops['FECHA'] = pd.to_datetime(df_ops['FECHA'])
        return df_ops, df_maint, df_faenas
    else:
        st.error("No se pudo descargar el archivo de Google Drive.")
        st.stop()

# --- Obtener datos cacheados
try:
    df_ops, df_maint, df_faenas = load_data_from_drive()
except Exception as e:
    st.error(f"Error cargando datos: {e}")
    st.stop()

# --- Sidebar: Filtros
st.sidebar.header("Filtros")
# N° de máquina
maquinas = df_ops['NUMERO_MAQ'].unique()
selected_maq = st.sidebar.selectbox("Selecciona N° de Máquina", sorted(maquinas))

# Mes disponible según la máquina seleccionada
df_ops_maq = df_ops[df_ops['NUMERO_MAQ'] == selected_maq]
meses_disponibles = df_ops_maq['FECHA'].dt.to_period('M').unique()
selected_mes = st.sidebar.selectbox(
    "Selecciona Mes",
    sorted([str(m) for m in meses_disponibles])
)
# Filtrar por mes y máquina
periodo = pd.Period(selected_mes)
df_filtrado = df_ops_maq[df_ops_maq['FECHA'].dt.to_period('M') == periodo]

# Faenas disponibles para ese mes y máquina
faenas_disponibles = df_filtrado['FAENA'].dropna().unique()
# Mostrar checkboxes para faenas
st.sidebar.markdown("#### Selecciona Faenas (con ticket):")
faenas_check = {}
for faena in sorted(faenas_disponibles):
    faenas_check[faena] = st.sidebar.checkbox(faena, value=True)
faenas_seleccionadas = [f for f, checked in faenas_check.items() if checked]
# Aplicar filtro por faena
df_filtrado = df_filtrado[df_filtrado['FAENA'].isin(faenas_seleccionadas)]

# --- Parte superior: Datos de la máquina y mantención
col1, col2, col3, col4 = st.columns(4)
# Nombre de la máquina (puede haber varios, tomamos el primero del mes)
nombre_maquina = df_filtrado['NOMBRE_MAQUINA'].iloc[0] if not df_filtrado.empty else ""
col1.metric("N° Máquina", selected_maq)
col2.metric("Nombre Máquina", nombre_maquina)

# Horómetro actual (último histórico de la máquina)
df_maq_all = df_ops[df_ops['NUMERO_MAQ'] == selected_maq]
registro_mas_reciente = df_maq_all.sort_values('FECHA').iloc[-1]
horometro_actual = registro_mas_reciente['HOROMETRO_FINAL']

# Buscar en hoja MANTENIMIENTOS
df_maint_maq = df_maint[df_maint['NRO_MAQUINA'] == selected_maq].sort_values("FECHA ULTIMO MANTENIMIENTO")
if not df_maint_maq.empty:
    ultimo_maint = df_maint_maq.iloc[-1]
    horas_ult_mant = ultimo_maint['HORAS AL ULTIMO MANTENIMIENTO']
    intervalo_mant = ultimo_maint['HORAS ENTRE CADA MANTENCIÓN']
else:
    horas_ult_mant = 0
    intervalo_mant = 500  # Valor por defecto si no está definido

horas_desde_mant = horometro_actual - horas_ult_mant
horas_para_prox = intervalo_mant - horas_desde_mant

# Semáforo
if horas_para_prox <= 0:
    semaforo = "🔴"
elif horas_para_prox <= 50:
    semaforo = "🟡"
else:
    semaforo = "🟢"

col3.metric("Horas para Próxima Mantención", f"{horas_para_prox:.0f}")
col4.metric("Estado Mantención", semaforo)

st.markdown("---")

# --- Parte inferior: Gráficos
st.subheader("Consumo de Petróleo Diario (Litros)")
if not df_filtrado.empty:
    consumo_diario = df_filtrado.groupby(df_filtrado['FECHA'].dt.day)['TOTAL_LTS'].sum()
    st.bar_chart(consumo_diario)
else:
    st.info("No hay datos para los filtros seleccionados.")

st.subheader("Rendimiento Diario: Real vs Ideal (Litros/Hora)")
if not df_filtrado.empty:
    # Real: promedio por día
    rendimiento_real = df_filtrado.groupby(df_filtrado['FECHA'].dt.day)['RENDIMIENTO_HORA'].mean()
    # Ideal: buscar el rendimiento ideal por día y faena en la hoja FAENAS
    rendimiento_ideal = []
    for idx, row in df_filtrado.iterrows():
        faena = row['FAENA']
        # Buscar rendimiento ideal en la hoja FAENAS para esa faena
        ideal_row = df_faenas[df_faenas['FAENA'] == faena]
        if not ideal_row.empty:
            valor_ideal = ideal_row['RENDIMIENTO POR HORA'].iloc[0]
        else:
            valor_ideal = np.nan
        rendimiento_ideal.append(valor_ideal)
    df_rend = pd.DataFrame({
        'Día': df_filtrado['FECHA'].dt.day,
        'Rendimiento Real': df_filtrado['RENDIMIENTO_HORA'],
        'Rendimiento Ideal': rendimiento_ideal
    })
    # Agrupar por día para mostrar promedio
    rendimiento_ideal_diario = df_rend.groupby('Día')['Rendimiento Ideal'].mean()
    # Plot ambas líneas
    import matplotlib.pyplot as plt
    plt.figure(figsize=(10, 5))
    plt.plot(rendimiento_real.index, rendimiento_real.values, 'o-', color='black', label='Real')
    plt.plot(rendimiento_ideal_diario.index, rendimiento_ideal_diario.values, 'o-', color='blue', label='Ideal')
    plt.xlabel("Día del Mes")
    plt.ylabel("Rendimiento (L/Hr)")
    plt.title("Rendimiento Diario: Real vs Ideal")
    plt.legend()
    st.pyplot(plt)
else:
    st.info("No hay datos para los filtros seleccionados.")

st.markdown("---")
st.caption("Datos actualizados al: " + str(df_ops['FECHA'].max().date()))

