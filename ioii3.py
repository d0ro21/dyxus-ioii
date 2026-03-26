import streamlit as st
import pandas as pd
import gurobipy as gp
from gurobipy import GRB
import matplotlib.pyplot as plt
import math

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Dashboard IOII - Burrito Game 3.0", layout="wide")
st.title("🌮 Burrito Game 3.0 - Otimização de Frota (IOII)")
st.markdown("Simulador de Programação Linear Inteira Mista (MILP) com restrições avançadas.")

# --- 2. UPLOAD DO FICHEIRO EXCEL ---
uploaded_file = st.file_uploader("Arraste e solte o ficheiro Excel (.xlsx) aqui", type=["xlsx"])

if uploaded_file is not None:
    try:
        df_demand = pd.read_excel(uploaded_file, sheet_name='demand_node_data')
        df_truck = pd.read_excel(uploaded_file, sheet_name='truck_node_data')
        df_prob = pd.read_excel(uploaded_file, sheet_name='problem_data')
        df_dt = pd.read_excel(uploaded_file, sheet_name='demand_truck_data')
        df_dt = df_dt[['demand_node_index', 'truck_node_index', 'scaled_demand']].dropna()
    except Exception as e:
        st.error(f"⚠️ Erro ao ler o Excel! Certifique-se de que tem as abas corretas. Detalhe: {e}")
        st.stop()

    default_r = float(df_prob['burrito_price'].iloc[0])
    default_k = float(df_prob['ingredient_cost'].iloc[0])
    
    # Extrair índices logo aqui para popular a interface (dropdowns)
    I = df_truck['index'].tolist()  # i: Localizações (Camiões)
    J = df_demand['index'].tolist() # j: Edifícios (Procura)

    # --- 3. BARRA LATERAL (MARKETING E FROTA) ---
    st.sidebar.header("🎯 Estratégia de Marketing")
    aumento_pct = st.sidebar.slider("Aumento Procura / Campanha (%)", min_value=1, max_value=50, value=10) / 100.0
    max_campanhas = st.sidebar.slider("Máx. Campanhas por Edifício", min_value=0, max_value=5, value=3)
    custo_campanha = st.sidebar.number_input("Custo de 1 Campanha (€)", min_value=0.0, value=20.0, step=10.0)
    orcamento_mkt = st.sidebar.number_input("Orçamento Total Marketing (€)", min_value=0.0, value=500.0, step=50.0)

    st.sidebar.markdown("---")

    st.sidebar.header("⚙️ Parâmetros Financeiros")
    r = st.sidebar.number_input("Preço de Venda do Burrito (€)", min_value=1.0, value=default_r, step=0.5)
    k_ing = st.sidebar.number_input("Custo dos Ingredientes (€)", min_value=0.5, value=default_k, step=0.5)

    st.sidebar.markdown("---")
    st.sidebar.header("🚚 Frota (Tamanhos e Custos)")
    col_cap, col_cost = st.sidebar.columns(2)
    with col_cap:
        cap_P = st.number_input("Cap. Pequeno", min_value=10, value=25, step=5)
        cap_M = st.number_input("Cap. Médio", min_value=10, value=50, step=5)
        cap_G = st.number_input("Cap. Grande", min_value=10, value=100, step=10)
    with col_cost:
        cost_P = st.number_input("Custo Peq (€)", min_value=0, value=150, step=10)
        cost_M = st.number_input("Custo Méd (€)", min_value=0, value=250, step=10)
        cost_G = st.number_input("Custo Grd (€)", min_value=0, value=400, step=10)

    st.sidebar.markdown("---")
    st.sidebar.header("🛡️ Restrições Avançadas (Fase 3)")
    
    use_monopolio = st.sidebar.checkbox("1. Monopólio Zonal (Camiões Grandes)", value=True)
    raio_monopolio = st.sidebar.number_input("Raio de Exclusividade (m)", min_value=10.0, value=150.0, step=10.0) if use_monopolio else 0.0
    
    use_quadrantes = st.sidebar.checkbox("2. Cobertura Geográfica (1 por Quadrante)", value=True)
    
    use_guerra = st.sidebar.checkbox("3. Exclusividade de Clientes Rivais", value=True)
    if use_guerra:
        cliente_rival_1 = st.sidebar.selectbox("Cliente A:", options=J, index=J.index('demand1') if 'demand1' in J else 0)
        cliente_rival_2 = st.sidebar.selectbox("Cliente B:", options=J, index=J.index('demand18') if 'demand18' in J else 1)
    else:
        cliente_rival_1 = None
        cliente_rival_2 = None

    TIPOS = ['Pequeno', 'Médio', 'Grande']
    CAPACIDADE = {'Pequeno': cap_P, 'Médio': cap_M, 'Grande': cap_G}
    CUSTO_FIXO = {'Pequeno': cost_P, 'Médio': cost_M, 'Grande': cost_G}
    CORES_TAMANHO = {'Pequeno': 'lightblue', 'Médio': 'dodgerblue', 'Grande': 'darkblue'}
    SIZES_GRAFICO = {'Pequeno': 150, 'Médio': 300, 'Grande': 500}

    # --- 4. OTIMIZAÇÃO GUROBI ---
    if st.button("🚀 Otimizar Frota (Correr Gurobi)", type="primary"):
        with st.spinner("A calcular a rede ótima MILP..."):
            
            # Matriz de Procura: a_ij
            a = {(row['truck_node_index'], row['demand_node_index']): row['scaled_demand'] for _, row in df_dt.iterrows()}

            env = gp.Env(empty=True)
            env.setParam("OutputFlag", 0)
            env.start()
            model = gp.Model("Burrito_Game_Fase_3", env=env)

            # Variáveis de Decisão
            Y = model.addVars(I, TIPOS, vtype=GRB.BINARY, name="Y") # y_it
            X = model.addVars(I, J, vtype=GRB.BINARY, name="X")     # x_ij
            P = model.addVars(J, vtype=GRB.INTEGER, lb=0, ub=max_campanhas, name="Marketing") # P_j
            Z = model.addVars(I, J, vtype=GRB.CONTINUOUS, name="Z_Procura")                   # Z_ij

            # Função Objetivo
            lucro_var = gp.quicksum((r - k_ing) * Z[i, j] for i in I for j in J if (i, j) in a)
            custo_fixo_total = gp.quicksum(CUSTO_FIXO[t] * Y[i, t] for i in I for t in TIPOS)
            custo_mkt_total = gp.quicksum(custo_campanha * P[j] for j in J)
            model.setObjective(lucro_var - custo_fixo_total - custo_mkt_total, GRB.MAXIMIZE)

            # Restrições Base
            for j in J:
                model.addConstr(gp.quicksum(X[i, j] for i in I if (i, j) in a) <= 1)
                
            for i in I:
                model.addConstr(gp.quicksum(Y[i, t] for t in TIPOS) <= 1)

            # Linearização Z
            for i in I:
                for j in J:
                    if (i, j) in a:
                        d_base = a[i, j]
                        U_ij = d_base * (1 + aumento_pct * max_campanhas)
                        model.addConstr(Z[i, j] <= U_ij * X[i, j])
                        model.addConstr(Z[i, j] <= d_base + (aumento_pct * d_base) * P[j])
                        model.addConstr(Z[i, j] >= d_base + (aumento_pct * d_base) * P[j] - U_ij * (1 - X[i, j]))

            # Orçamento e Capacidade
            model.addConstr(gp.quicksum(custo_campanha * P[j] for j in J) <= orcamento_mkt)
            for i in I:
                model.addConstr(gp.quicksum(Z[i, j] for j in J if (i, j) in a) <= gp.quicksum(CAPACIDADE[t] * Y[i, t] for t in TIPOS))

            # --- RESTRIÇÕES FASE 3 ---
            
            # 1. Monopólio Zonal
            if use_monopolio:
                for i1 in I:
                    for i2 in I:
                        if i1 != i2:
                            row1 = df_truck[df_truck['index'] == i1].iloc[0]
                            row2 = df_truck[df_truck['index'] == i2].iloc[0]
                            dist = math.sqrt((row1['x'] - row2['x'])**2 + (row1['y'] - row2['y'])**2)
                            if dist <= raio_monopolio:
                                model.addConstr(Y[i1, 'Grande'] + gp.quicksum(Y[i2, t] for t in TIPOS) <= 1)

            # 2. Quadrantes
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

            # 3. Exclusividade de Clientes
            if use_guerra and cliente_rival_1 and cliente_rival_2:
                soma_j1 = gp.quicksum(X[i, cliente_rival_1] for i in I if (i, cliente_rival_1) in a)
                soma_j2 = gp.quicksum(X[i, cliente_rival_2] for i in I if (i, cliente_rival_2) in a)
                model.addConstr(soma_j1 + soma_j2 <= 1)

            model.optimize()

            if model.Status == GRB.OPTIMAL:
                st.success("✅ Solução Ótima Encontrada!")
                opened_trucks = [(i, t) for i in I for t in TIPOS if Y[i, t].X > 0.5]

                # Cálculos Financeiros
                total_burritos = sum(Z[i, j].X for i in I for j in J if (i, j) in a and X[i, j].X > 0.5)
                faturacao = total_burritos * r
                custo_ingredientes = total_burritos * k_ing
                custo_frota = sum(CUSTO_FIXO[t] for i, t in opened_trucks)
                custo_mkt_gasto = sum(P[j].X * custo_campanha for j in J)
                lucro_liquido = faturacao - custo_ingredientes - custo_frota - custo_mkt_gasto

                # Dash Financeiro
                st.subheader("📊 Resumo Financeiro da Operação")
                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("Faturação Bruta", f"{faturacao:,.2f} €")
                col2.metric("Custo Ingredientes", f"- {custo_ingredientes:,.2f} €")
                col3.metric("Custo Frota", f"- {custo_frota:,.2f} €")
                col4.metric("Custo Marketing", f"- {custo_mkt_gasto:,.2f} €")
                col5.metric("Lucro Líquido", f"{lucro_liquido:,.2f} €")
                st.markdown("---")

                # Guerra de Clientes (UI)
                if use_guerra:
                    j1_servido = sum(X[i, cliente_rival_1].X for i in I if (i, cliente_rival_1) in a) > 0.5
                    j2_servido = sum(X[i, cliente_rival_2].X for i in I if (i, cliente_rival_2) in a) > 0.5
                    st.subheader("⚔️ Conflito de Exclusividade")
                    if j1_servido:
                        st.info(f"O modelo escolheu servir o **{cliente_rival_1}**. O **{cliente_rival_2}** foi abandonado (Custo de Oportunidade).")
                    elif j2_servido:
                        st.info(f"O modelo escolheu servir o **{cliente_rival_2}**. O **{cliente_rival_1}** foi abandonado (Custo de Oportunidade).")
                    else:
                        st.warning(f"O modelo optou por NÃO SERVIR nenhum dos clientes rivais ({cliente_rival_1} e {cliente_rival_2}) para poupar recursos.")
                    st.markdown("---")

                # Gráfico
                st.subheader("🗺️ Mapa Logístico da Operação")
                fig, ax = plt.subplots(figsize=(10, 6))
                
                # Plot Quadrantes (linhas subtis)
                if use_quadrantes:
                    ax.axhline(y_medio, color='red', linestyle='--', alpha=0.3, label='Divisão Norte/Sul')
                    ax.axvline(x_medio, color='green', linestyle='--', alpha=0.3, label='Divisão Este/Oeste')

                ax.scatter(df_demand['x'], df_demand['y'], c='gray', s=30, label='Edifícios', alpha=0.5, zorder=2)

                for i, tipo in opened_trucks:
                    t_row = df_truck[df_truck['index'] == i].iloc[0]
                    ax.scatter(t_row['x'], t_row['y'], c=CORES_TAMANHO[tipo], marker='s', s=SIZES_GRAFICO[tipo], edgecolor='black', zorder=3, label=f'Camião {tipo}' if f'Camião {tipo}' not in ax.get_legend_handles_labels()[1] else "")
                    ax.text(t_row['x'], t_row['y'] + 10, f"{i}\n({tipo})", color='black', fontweight='bold', ha='center', fontsize=8)

                for j in J:
                    if P[j].X > 0.5:
                        d_row = df_demand[df_demand['index'] == j].iloc[0]
                        ax.scatter(d_row['x'], d_row['y'], c='gold', marker='*', s=200, edgecolor='black', zorder=4, label='Marketing Ativo' if 'Marketing Ativo' not in ax.get_legend_handles_labels()[1] else "")
                    
                    for i in I:
                        if (i, j) in a and X[i, j].X > 0.5:
                            d_row = df_demand[df_demand['index'] == j].iloc[0]
                            t_row = df_truck[df_truck['index'] == i].iloc[0]
                            ax.plot([d_row['x'], t_row['x']], [d_row['y'], t_row['y']], 'k-', alpha=0.2, zorder=1)

                handles, labels = plt.gca().get_legend_handles_labels()
                by_label = dict(zip(labels, handles))
                ax.legend(by_label.values(), by_label.keys(), loc='upper right')
                ax.grid(True, linestyle=':', alpha=0.4)
                st.pyplot(fig)
                st.markdown("---")

                # Tabelas
                st.subheader("📢 Estratégia de Marketing")
                mkt_data = []
                for j in J:
                    if P[j].X > 0.5:
                        camps = int(P[j].X)
                        base_demand = sum(a[i, j] * X[i, j].X for i in I if (i, j) in a and X[i, j].X > 0.5)
                        nova_procura = base_demand * (1 + aumento_pct * camps)
                        mkt_data.append({"Edifício": j, "Campanhas": camps, "Procura Base": round(base_demand, 1), "Nova Procura": round(nova_procura, 1), "Custo (€)": camps * custo_campanha})
                
                if len(mkt_data) > 0:
                    st.dataframe(pd.DataFrame(mkt_data), use_container_width=True, hide_index=True)
                else:
                    st.info("Nenhuma campanha considerada rentável.")

                col_tab1, col_tab2 = st.columns(2)
                with col_tab1:
                    st.subheader("🚚 Frota Instalada")
                    
                    def get_quadrante(i):
                        if not use_quadrantes: return "-"
                        row = df_truck[df_truck['index'] == i].iloc[0]
                        if row['x'] <= x_medio and row['y'] >= y_medio: return "Q1 (NO)"
                        if row['x'] > x_medio and row['y'] >= y_medio: return "Q2 (NE)"
                        if row['x'] <= x_medio and row['y'] < y_medio: return "Q3 (SO)"
                        return "Q4 (SE)"

                    frota_df = pd.DataFrame([{"Camião": i, "Quadrante": get_quadrante(i), "Tipo": t, "Cap.": CAPACIDADE[t], "Vendas": int(sum(Z[i, j].X for j in J if (i, j) in a and X[i, j].X > 0.5)), "Custo (€)": CUSTO_FIXO[t]} for i, t in opened_trucks])
                    st.dataframe(frota_df, use_container_width=True, hide_index=True)
                    
                with col_tab2:
                    st.subheader("🏢 Alocação de Edifícios")
                    st.dataframe(pd.DataFrame([{"Edifício": j, "Camião": i, "Tipo": next(t for t in TIPOS if Y[i, t].X > 0.5), "Burritos": round(Z[i, j].X, 1)} for j in J for i in I if (i, j) in a and X[i, j].X > 0.5]), use_container_width=True, hide_index=True)

            elif model.Status == GRB.INFEASIBLE:
                st.error("❌ O Modelo é INVIÁVEL. As restrições de Cobertura Geográfica e Monopólio Zonal em conjunto com o orçamento podem estar a estrangular a rede. Tente aumentar o preço de venda ou reduzir o raio de exclusividade.")
else:
    st.info("👆 Por favor, carregue o ficheiro Excel com os dados do 'Burrito Game' para desbloquear o simulador.")
