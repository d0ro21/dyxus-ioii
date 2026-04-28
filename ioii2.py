import streamlit as st
import pandas as pd
import gurobipy as gp
from gurobipy import GRB
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import math
import os
import time

# --- 0. SISTEMA DE TRADUÇÃO (ESTADO DA SESSÃO) ---
if 'lang' not in st.session_state:
    st.session_state['lang'] = 'PT'

def t(pt_text, en_text):
    """Função mágica de tradução: devolve PT ou EN consoante o botão escolhido."""
    return pt_text if st.session_state['lang'] == 'PT' else en_text

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Dashboard IOII - Burrito Game (MINLP)", layout="wide")

# O botão de idioma passa para o topo absoluto da barra lateral, fora de qualquer condição!
st.sidebar.radio("🌐 Idioma / Language", ['PT', 'EN'], horizontal=True, key='lang')
st.sidebar.markdown("---")

st.title(t("🌮 Burrito Game 3.0 - Otimização de Frota (MINLP)", "🌮 Burrito Game 3.0 - Fleet Optimization (MINLP)"))
st.markdown(t("Simulador de Programação Não-Linear com Gurobi WLS e Fila de Espera Automática.", 
              "Non-Linear Programming Simulator with Gurobi WLS and Automatic Queue."))

# --- 2. CARREGAMENTO DOS DADOS (Automático) ---
file_path = 'Data_Grupo1.xlsx'

try:
    df_demand = pd.read_excel(file_path, sheet_name='demand_node_data')
    df_truck = pd.read_excel(file_path, sheet_name='truck_node_data')
    df_prob = pd.read_excel(file_path, sheet_name='problem_data')
    df_dt = pd.read_excel(file_path, sheet_name='demand_truck_data')
    df_dt = df_dt[['demand_node_index', 'truck_node_index', 'scaled_demand']].dropna()
except Exception as e:
    st.error(t(f"⚠️ Erro ao ler o Excel! Certifique-se de que '{file_path}' está na pasta. Detalhe: {e}", 
               f"⚠️ Error reading Excel! Make sure '{file_path}' is in the folder. Detail: {e}"))
    st.stop()

default_r = float(df_prob['burrito_price'].iloc[0])
default_k = float(df_prob['ingredient_cost'].iloc[0])

I = df_truck['index'].tolist()
J = df_demand['index'].tolist()

# --- 3. BARRA LATERAL (Restante) ---
st.sidebar.header(t("🎯 Estratégia de Marketing", "🎯 Marketing Strategy"))
aumento_pct = st.sidebar.slider(t("Aumento Procura / Campanha (%)", "Demand Increase / Campaign (%)"), min_value=1, max_value=50, value=10) / 100.0
max_campanhas = st.sidebar.slider(t("Máx. Campanhas por Edifício", "Max Campaigns per Building"), min_value=0, max_value=5, value=3)
custo_campanha = st.sidebar.number_input(t("Custo de 1 Campanha (€)", "Cost of 1 Campaign (€)"), min_value=0.0, value=20.0, step=10.0)
orcamento_mkt = st.sidebar.number_input(t("Orçamento Total Marketing (€)", "Total Marketing Budget (€)"), min_value=0.0, value=500.0, step=50.0)

st.sidebar.markdown("---")

st.sidebar.header(t("⚙️ Parâmetros Financeiros", "⚙️ Financial Parameters"))
r = st.sidebar.number_input(t("Preço de Venda do Burrito (€)", "Burrito Selling Price (€)"), min_value=1.0, value=default_r, step=0.5)
k_ing = st.sidebar.number_input(t("Custo dos Ingredientes (€)", "Ingredients Cost (€)"), min_value=0.5, value=default_k, step=0.5)

st.sidebar.markdown("---")
st.sidebar.header(t("🚚 Frota (Tamanhos e Custos)", "🚚 Fleet (Sizes & Costs)"))
col_cap, col_cost = st.sidebar.columns(2)
with col_cap:
    cap_P = st.number_input(t("Cap. Pequeno", "Small Cap."), min_value=10, value=25, step=5)
    cap_M = st.number_input(t("Cap. Médio", "Medium Cap."), min_value=10, value=50, step=5)
    cap_G = st.number_input(t("Cap. Grande", "Large Cap."), min_value=10, value=100, step=10)
with col_cost:
    cost_P = st.number_input(t("Custo Peq (€)", "Small Cost (€)"), min_value=0, value=150, step=10)
    cost_M = st.number_input(t("Custo Méd (€)", "Medium Cost (€)"), min_value=0, value=250, step=10)
    cost_G = st.number_input(t("Custo Grd (€)", "Large Cost (€)"), min_value=0, value=400, step=10)

st.sidebar.markdown("---")
st.sidebar.header(t("🛡️ Restrições Avançadas", "🛡️ Advanced Constraints"))

use_monopolio = st.sidebar.checkbox(t("Monopólio Zonal (Camiões Grandes)", "Zonal Monopoly (Large Trucks)"), value=True)
raio_monopolio = st.sidebar.number_input(t("Raio de Exclusividade do Grande (m)", "Exclusivity Radius (m)"), min_value=10.0, value=150.0, step=10.0) if use_monopolio else 0.0

use_dist_minima = st.sidebar.checkbox(t("Distância Mínima de Segurança (Todos)", "Minimum Safety Distance (All)"), value=True)
raio_dist_minima = st.sidebar.number_input(t("Raio Mínimo entre Camiões (m)", "Min Radius between Trucks (m)"), min_value=10.0, value=50.0, step=10.0) if use_dist_minima else 0.0

use_quadrantes = st.sidebar.checkbox(t("Cobertura Geográfica (1 por Quadrante)", "Geographic Coverage (1 per Quadrant)"), value=True)

use_min_trucks = st.sidebar.checkbox(t("Impor nº mínimo total de camiões?", "Enforce minimum total trucks?"), value=use_quadrantes)
min_val_admitido = 4 if use_quadrantes else 1
if use_min_trucks:
    min_trucks = st.sidebar.number_input(t("Nº Mínimo de Camiões", "Min Number of Trucks"), min_value=min_val_admitido, value=max(4, min_val_admitido), step=1)
else:
    min_trucks = 0

st.sidebar.markdown("---")
use_guerra = st.sidebar.checkbox(t("Exclusividade de Clientes Rivais", "Rival Clients Exclusivity"), value=True)
if use_guerra:
    cliente_rival_1 = st.sidebar.selectbox(t("Cliente A:", "Client A:"), options=J, index=J.index('demand1') if 'demand1' in J else 0)
    cliente_rival_2 = st.sidebar.selectbox(t("Cliente B:", "Client B:"), options=J, index=J.index('demand18') if 'demand18' in J else 1)
else:
    cliente_rival_1, cliente_rival_2 = None, None

TIPOS = ['Pequeno', 'Médio', 'Grande']
CAPACIDADE = {'Pequeno': cap_P, 'Médio': cap_M, 'Grande': cap_G}
CUSTO_FIXO = {'Pequeno': cost_P, 'Médio': cost_M, 'Grande': cost_G}
CORES_TAMANHO = {'Pequeno': 'lightblue', 'Médio': 'dodgerblue', 'Grande': 'darkblue'}
SIZES_GRAFICO = {'Pequeno': 150, 'Médio': 300, 'Grande': 500}

def tipo_trad(t_key):
    trad_dict = {'Pequeno': 'Small', 'Médio': 'Medium', 'Grande': 'Large'}
    return t(t_key, trad_dict[t_key])

# --- 4. OTIMIZAÇÃO GUROBI (MINLP) COM FILA DE ESPERA ---
if st.button(t("🚀 Otimizar Rede (Modelo Não-Linear)", "🚀 Optimize Network (Non-Linear Model)"), type="primary"):
    with st.spinner(t("A calcular... (Pode demorar uns segundos extra na fila 🚦)", "Calculating... (May take a few extra seconds in queue 🚦)")):
        
        sucesso_gurobi = False
        a = {(row['truck_node_index'], row['demand_node_index']): row['scaled_demand'] for _, row in df_dt.iterrows()}
        
        for tentativa in range(5):
            try:
                env = gp.Env(empty=True)
                env.setParam("OutputFlag", 0)
                
                if "gurobi" in st.secrets:
                    env.setParam("WLSACCESSID", st.secrets["gurobi"]["WLSACCESSID"])
                    env.setParam("WLSSECRET", st.secrets["gurobi"]["WLSSECRET"])
                    env.setParam("LICENSEID", st.secrets["gurobi"]["LICENSEID"])
                
                env.start()
                model = gp.Model("Burrito_Game_MINLP", env=env)
                model.setParam('NonConvex', 2)

                Y = model.addVars(I, TIPOS, vtype=GRB.BINARY, name="Y")
                X = model.addVars(I, J, vtype=GRB.BINARY, name="X")
                P = model.addVars(J, vtype=GRB.INTEGER, lb=0, ub=max_campanhas, name="Marketing")
                Z = model.addVars(I, J, vtype=GRB.CONTINUOUS, name="Z_Procura")

                lucro_var = gp.quicksum((r - k_ing) * Z[i, j] for i in I for j in J if (i, j) in a)
                custo_fixo_total = gp.quicksum(CUSTO_FIXO[t] * Y[i, t] for i in I for t in TIPOS)
                custo_mkt_total = gp.quicksum(custo_campanha * P[j] for j in J)
                model.setObjective(lucro_var - custo_fixo_total - custo_mkt_total, GRB.MAXIMIZE)

                for j in J:
                    model.addConstr(gp.quicksum(X[i, j] for i in I if (i, j) in a) <= 1)
                for i in I:
                    model.addConstr(gp.quicksum(Y[i, t] for t in TIPOS) <= 1)

                for i in I:
                    for j in J:
                        if (i, j) in a:
                            d_base = a[i, j]
                            model.addConstr(Z[i, j] == d_base * X[i, j] + (d_base * aumento_pct) * X[i, j] * P[j])

                model.addConstr(gp.quicksum(custo_campanha * P[j] for j in J) <= orcamento_mkt)
                for i in I:
                    model.addConstr(gp.quicksum(Z[i, j] for j in J if (i, j) in a) <= gp.quicksum(CAPACIDADE[t] * Y[i, t] for t in TIPOS))

                if use_min_trucks and min_trucks > 0:
                    model.addConstr(gp.quicksum(Y[i, t] for i in I for t in TIPOS) >= min_trucks)

                if use_monopolio or use_dist_minima:
                    for i1 in I:
                        for i2 in I:
                            if i1 < i2: 
                                row1 = df_truck[df_truck['index'] == i1].iloc[0]
                                row2 = df_truck[df_truck['index'] == i2].iloc[0]
                                dist = math.sqrt((row1['x'] - row2['x'])**2 + (row1['y'] - row2['y'])**2)
                                
                                if use_dist_minima and dist <= raio_dist_minima:
                                    model.addConstr(gp.quicksum(Y[i1, t] for t in TIPOS) + gp.quicksum(Y[i2, t] for t in TIPOS) <= 1)
                                
                                if use_monopolio and dist <= raio_monopolio:
                                    model.addConstr(Y[i1, 'Grande'] + gp.quicksum(Y[i2, t] for t in TIPOS) <= 1)
                                    model.addConstr(Y[i2, 'Grande'] + gp.quicksum(Y[i1, t] for t in TIPOS) <= 1)

                if use_quadrantes:
                    x_medio = df_truck['x'].mean()
                    y_medio = df_truck['y'].mean()
                    Q1, Q2, Q3, Q4 = [], [], [], []
                    for i in I:
                        row = df_truck[df_truck['index'] == i].iloc[0]
                        if row['x'] <= x_medio and row['y'] >= y_medio: Q1.append(i)
                        elif row['x'] > x_medio and row['y'] >= y_medio: Q2.append(i)
                        elif row['x'] <= x_medio and row['y'] < y_medio: Q3.append(i)
                        else: Q4.append(i)
                    for quadrante in [Q1, Q2, Q3, Q4]:
                        if len(quadrante) > 0:
                            model.addConstr(gp.quicksum(Y[i, t] for i in quadrante for t in TIPOS) >= 1)

                if use_guerra and cliente_rival_1 and cliente_rival_2:
                    soma_j1 = gp.quicksum(X[i, cliente_rival_1] for i in I if (i, cliente_rival_1) in a)
                    soma_j2 = gp.quicksum(X[i, cliente_rival_2] for i in I if (i, cliente_rival_2) in a)
                    model.addConstr(soma_j1 + soma_j2 <= 1)

                model.optimize()

                if model.Status == GRB.OPTIMAL:
                    st.success(t("✅ Solução Não-Linear Ótima Encontrada!", "✅ Optimal Non-Linear Solution Found!"))
                    opened_trucks = [(i, t) for i in I for t in TIPOS if Y[i, t].X > 0.5]

                    total_burritos = sum(Z[i, j].X for i in I for j in J if (i, j) in a and X[i, j].X > 0.5)
                    faturacao = total_burritos * r
                    custo_ingredientes = total_burritos * k_ing
                    custo_frota = sum(CUSTO_FIXO[t] for i, t in opened_trucks)
                    custo_mkt_gasto = sum(P[j].X * custo_campanha for j in J)
                    lucro_liquido = faturacao - custo_ingredientes - custo_frota - custo_mkt_gasto

                    st.subheader(t("📊 Resumo Financeiro da Operação (MINLP)", "📊 Financial Operation Summary (MINLP)"))
                    col1, col2, col3, col4, col5 = st.columns(5)
                    col1.metric(t("Faturação Bruta", "Gross Revenue"), f"{faturacao:,.2f} €")
                    col2.metric(t("Custo Ingredientes", "Ingredients Cost"), f"- {custo_ingredientes:,.2f} €")
                    col3.metric(t("Custo Frota", "Fleet Cost"), f"- {custo_frota:,.2f} €")
                    col4.metric(t("Custo Marketing", "Marketing Cost"), f"- {custo_mkt_gasto:,.2f} €")
                    col5.metric(t("Lucro Líquido", "Net Profit"), f"{lucro_liquido:,.2f} €")
                    st.markdown("---")

                    if use_guerra:
                        j1_servido = sum(X[i, cliente_rival_1].X for i in I if (i, cliente_rival_1) in a) > 0.5
                        j2_servido = sum(X[i, cliente_rival_2].X for i in I if (i, cliente_rival_2) in a) > 0.5
                        st.subheader(t("⚔️ Conflito de Exclusividade", "⚔️ Exclusivity Conflict"))
                        if j1_servido:
                            st.info(t(f"O modelo escolheu servir o **{cliente_rival_1}**. O **{cliente_rival_2}** foi abandonado.", 
                                      f"The model chose to serve **{cliente_rival_1}**. **{cliente_rival_2}** was abandoned."))
                        elif j2_servido:
                            st.info(t(f"O modelo escolheu servir o **{cliente_rival_2}**. O **{cliente_rival_1}** foi abandonado.",
                                      f"The model chose to serve **{cliente_rival_2}**. **{cliente_rival_1}** was abandoned."))
                        else:
                            st.warning(t("O modelo optou por NÃO SERVIR nenhum dos clientes rivais.", "The model opted NOT TO SERVE any rival clients."))
                        st.markdown("---")

                    st.subheader(t("🗺️ Mapa Logístico da Operação", "🗺️ Operation Logistics Map"))
                    fig, ax = plt.subplots(figsize=(10, 6))
                    
                    img_path = 'mapa.png'
                    if os.path.exists(img_path):
                        try:
                            img = mpimg.imread(img_path)
                            all_x = pd.concat([df_demand['x'], df_truck['x']])
                            all_y = pd.concat([df_demand['y'], df_truck['y']])
                            extent = [all_x.min(), all_x.max(), all_y.min(), all_y.max()]
                            ax.imshow(img, extent=extent, aspect='auto', alpha=0.6, zorder=0)
                        except Exception as e:
                            st.warning(t(f"⚠️ Erro ao carregar a imagem de fundo: {e}", f"⚠️ Error loading background image: {e}"))

                    if use_quadrantes:
                        ax.axhline(y_medio, color='red', linestyle='--', alpha=0.3, label=t('Divisão Norte/Sul', 'North/South Division'))
                        ax.axvline(x_medio, color='green', linestyle='--', alpha=0.3, label=t('Divisão Este/Oeste', 'East/West Division'))

                    ax.scatter(df_demand['x'], df_demand['y'], c='gray', s=30, label=t('Edifícios', 'Buildings'), alpha=0.8, zorder=2)

                    for i, tipo in opened_trucks:
                        t_row = df_truck[df_truck['index'] == i].iloc[0]
                        tipo_nome = tipo_trad(tipo)
                        lbl = t(f'Camião {tipo}', f'{tipo_nome} Truck')
                        ax.scatter(t_row['x'], t_row['y'], c=CORES_TAMANHO[tipo], marker='s', s=SIZES_GRAFICO[tipo], edgecolor='black', zorder=3, label=lbl if lbl not in ax.get_legend_handles_labels()[1] else "")
                        ax.text(t_row['x'], t_row['y'] + 10, f"{i}\n({tipo_nome[0]})", color='black', fontweight='bold', ha='center', fontsize=8)

                    for j in J:
                        if P[j].X > 0.5:
                            d_row = df_demand[df_demand['index'] == j].iloc[0]
                            ax.scatter(d_row['x'], d_row['y'], c='gold', marker='*', s=200, edgecolor='black', zorder=4, label=t('Marketing Ativo', 'Active Marketing') if t('Marketing Ativo', 'Active Marketing') not in ax.get_legend_handles_labels()[1] else "")
                        
                        for i in I:
                            if (i, j) in a and X[i, j].X > 0.5:
                                d_row = df_demand[df_demand['index'] == j].iloc[0]
                                t_row = df_truck[df_truck['index'] == i].iloc[0]
                                ax.plot([d_row['x'], t_row['x']], [d_row['y'], t_row['y']], 'k-', alpha=0.4, zorder=1)

                    handles, labels = plt.gca().get_legend_handles_labels()
                    by_label = dict(zip(labels, handles))
                    ax.legend(by_label.values(), by_label.keys(), loc='upper right')
                    ax.grid(False) 
                    st.pyplot(fig)
                    st.markdown("---")

                    col_tab1, col_tab2 = st.columns(2)
                    with col_tab1:
                        st.subheader(t("🚚 Frota Instalada", "🚚 Installed Fleet"))
                        def get_quadrante(i):
                            if not use_quadrantes: return "-"
                            row = df_truck[df_truck['index'] == i].iloc[0]
                            if row['x'] <= x_medio and row['y'] >= y_medio: return "Q1 (NO/NW)"
                            if row['x'] > x_medio and row['y'] >= y_medio: return "Q2 (NE)"
                            if row['x'] <= x_medio and row['y'] < y_medio: return "Q3 (SO/SW)"
                            return "Q4 (SE)"

                        frota_df = pd.DataFrame([{
                            t("Camião", "Truck"): i, 
                            t("Quadrante", "Quadrant"): get_quadrante(i), 
                            t("Tipo", "Type"): tipo_trad(tipo), 
                            t("Cap.", "Cap."): CAPACIDADE[tipo], 
                            t("Vendas Totais", "Total Sales"): int(sum(Z[i, j].X for j in J if (i, j) in a and X[i, j].X > 0.5)), 
                            "Custo (€) / Cost (€)": CUSTO_FIXO[tipo]
                        } for i, tipo in opened_trucks])
                        st.dataframe(frota_df, use_container_width=True, hide_index=True)
                        
                    with col_tab2:
                        st.subheader(t("📢 Estratégia de Marketing", "📢 Marketing Strategy"))
                        mkt_data = []
                        for j in J:
                            if P[j].X > 0.5:
                                camps = int(P[j].X)
                                base_demand = sum(a[i, j] * X[i, j].X for i in I if (i, j) in a and X[i, j].X > 0.5)
                                nova_procura = base_demand * (1 + aumento_pct * camps)
                                mkt_data.append({
                                    t("Edifício", "Building"): j, 
                                    t("Campanhas", "Campaigns"): camps, 
                                    t("Procura Nova", "New Demand"): round(nova_procura, 1)
                                })
                        if len(mkt_data) > 0:
                            st.dataframe(pd.DataFrame(mkt_data), use_container_width=True, hide_index=True)
                        else:
                            st.info(t("Nenhuma campanha de marketing ativada.", "No marketing campaigns activated."))

                    st.markdown("---")
                    st.subheader(t("📦 Detalhe de Vendas (Alocação Camião -> Edifício)", "📦 Sales Details (Truck -> Building Allocation)"))
                    vendas_data = []
                    for i in I:
                        for j in J:
                            if (i, j) in a and X[i, j].X > 0.5:
                                vendas_data.append({
                                    t("Camião", "Truck"): i,
                                    t("Edifício", "Building"): j,
                                    t("Burritos Entregues", "Burritos Delivered"): int(round(Z[i, j].X, 0))
                                })
                    
                    if vendas_data:
                        df_vendas = pd.DataFrame(vendas_data).sort_values(by=t("Camião", "Truck"))
                        st.dataframe(df_vendas, use_container_width=True, hide_index=True)
                    else:
                        st.info(t("Nenhuma venda registada pelo modelo.", "No sales recorded by the model."))

                elif model.Status in [GRB.INFEASIBLE, GRB.INF_OR_UNBD]:
                    st.error(t("❌ O Modelo é INVIÁVEL. Não existe nenhuma solução matemática possível com estas regras.", 
                               "❌ The Model is INFEASIBLE. No mathematical solution is possible with these rules."))
                    st.info(t("💡 **Dica:** O problema está demasiado estrangulado. Tente diminuir o 'Raio Mínimo entre Camiões', baixar o 'Nº Mínimo de Camiões' ou desligar alguma restrição de monopólio.",
                              "💡 **Tip:** The problem is too tight. Try decreasing the 'Min Radius between Trucks', lowering the 'Min Number of Trucks', or turning off a monopoly constraint."))
                else:
                    st.warning(t(f"⚠️ O otimizador parou sem encontrar a solução perfeita (Código de Status Gurobi: {model.Status}).",
                                 f"⚠️ The optimizer stopped without finding a perfect solution (Gurobi Status Code: {model.Status})."))
                    
                model.dispose()
                env.dispose()
                
                sucesso_gurobi = True
                break 
                
            except gp.GurobiError as e:
                if "overage" in str(e).lower() or "session" in str(e).lower() or "limit" in str(e).lower():
                    time.sleep(3)
                else:
                    st.error(t(f"⚠️ Erro matemático Gurobi: {e}", f"⚠️ Gurobi Math Error: {e}"))
                    break

        if not sucesso_gurobi:
            st.warning(t("🚦 A sala está toda a tentar ao mesmo tempo e os servidores esgotaram as vagas de espera! Por favor, aguarde 5 segundinhos e clique em Otimizar novamente.",
                         "🚦 The whole class is trying at the same time and servers are busy! Please wait 5 seconds and click Optimize again."))
