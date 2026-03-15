import streamlit as st
import pandas as pd
import gurobipy as gp
from gurobipy import GRB
import matplotlib.pyplot as plt
import math

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Dashboard IOII - Burrito Game", layout="wide")
st.title("🌮 Burrito Game - Otimização de Frota (IOII)")
st.markdown("Faça o upload do seu ficheiro Excel com os dados do problema para começar.")

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

    # --- 3. BARRA LATERAL (MARKETING E FROTA) ---
    st.sidebar.header("🎯 Estratégia de Marketing")
    aumento_pct = st.sidebar.slider("Aumento Procura / Campanha (%)", min_value=1, max_value=50, value=10) / 100.0
    max_campanhas = st.sidebar.slider("Máx. Campanhas por Edifício", min_value=0, max_value=5, value=3)
    custo_campanha = st.sidebar.number_input("Custo de 1 Campanha (€)", min_value=0.0, value=50.0, step=10.0)
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
    st.sidebar.header("🛡️ Outras Restrições")
    use_min_trucks = st.sidebar.checkbox("Impor nº mínimo total de camiões?")
    min_trucks = st.sidebar.number_input("Nº Mínimo de Camiões", min_value=1, value=2, step=1) if use_min_trucks else 0

    use_min_dist = st.sidebar.checkbox("Impor distância mínima entre camiões?")
    min_dist = st.sidebar.number_input("Distância Mínima", min_value=10.0, value=100.0, step=10.0) if use_min_dist else 0.0

    TIPOS = ['Pequeno', 'Médio', 'Grande']
    CAPACIDADE = {'Pequeno': cap_P, 'Médio': cap_M, 'Grande': cap_G}
    CUSTO_FIXO = {'Pequeno': cost_P, 'Médio': cost_M, 'Grande': cost_G}
    CORES_TAMANHO = {'Pequeno': 'lightblue', 'Médio': 'dodgerblue', 'Grande': 'darkblue'}
    SIZES_GRAFICO = {'Pequeno': 150, 'Médio': 300, 'Grande': 500}

    # --- 4. OTIMIZAÇÃO GUROBI ---
    if st.button("🚀 Otimizar Frota (Correr Gurobi)", type="primary"):
        with st.spinner("A calcular a rede ótima e marketing..."):
            I = df_demand['index'].tolist()
            J = df_truck['index'].tolist()
            a = {(row['demand_node_index'], row['truck_node_index']): row['scaled_demand'] for _, row in df_dt.iterrows()}

            env = gp.Env(empty=True)
            env.setParam("OutputFlag", 0)
            env.start()
            model = gp.Model("Burrito_Game_Marketing", env=env)

            Y = model.addVars(J, TIPOS, vtype=GRB.BINARY, name="Y")
            X = model.addVars(I, J, vtype=GRB.BINARY, name="X")

            # Variáveis do Marketing e Linearização (Z)
            M = model.addVars(I, vtype=GRB.INTEGER, lb=0, ub=max_campanhas, name="Marketing")
            Z = model.addVars(I, J, vtype=GRB.CONTINUOUS, name="Z_Procura")

            # Função Objetivo
            lucro_var = gp.quicksum((r - k_ing) * Z[i, j] for i in I for j in J if (i, j) in a)
            custo_fixo_total = gp.quicksum(CUSTO_FIXO[t] * Y[j, t] for j in J for t in TIPOS)
            custo_mkt_total = gp.quicksum(custo_campanha * M[i] for i in I)
            model.setObjective(lucro_var - custo_fixo_total - custo_mkt_total, GRB.MAXIMIZE)

            # Restrições
            for i in I:
                model.addConstr(gp.quicksum(X[i, j] for j in J if (i, j) in a) <= 1)
            for j in J:
                model.addConstr(gp.quicksum(Y[j, t] for t in TIPOS) <= 1)

            for i in I:
                for j in J:
                    if (i, j) in a:
                        d_base = a[i, j]
                        d_maxima = d_base * (1 + aumento_pct * max_campanhas)
                        model.addConstr(Z[i, j] <= d_maxima * X[i, j])
                        model.addConstr(Z[i, j] <= d_base + (aumento_pct * d_base) * M[i])
                        model.addConstr(Z[i, j] >= d_base + (aumento_pct * d_base) * M[i] - d_maxima * (1 - X[i, j]))

            model.addConstr(gp.quicksum(custo_campanha * M[i] for i in I) <= orcamento_mkt)

            for j in J:
                model.addConstr(gp.quicksum(Z[i, j] for i in I if (i, j) in a) <= gp.quicksum(CAPACIDADE[t] * Y[j, t] for t in TIPOS))

            if use_min_trucks:
                model.addConstr(gp.quicksum(Y[j, t] for j in J for t in TIPOS) >= min_trucks)
            if use_min_dist:
                for j1 in J:
                    for j2 in J:
                        if j1 < j2:
                            row1 = df_truck[df_truck['index'] == j1].iloc[0]
                            row2 = df_truck[df_truck['index'] == j2].iloc[0]
                            dist = math.sqrt((row1['x'] - row2['x'])**2 + (row1['y'] - row2['y'])**2)
                            if dist < min_dist:
                                model.addConstr(gp.quicksum(Y[j1, t] for t in TIPOS) + gp.quicksum(Y[j2, t] for t in TIPOS) <= 1)

            model.optimize()

            if model.Status == GRB.OPTIMAL:
                st.success("✅ Solução Ótima Encontrada!")
                opened_trucks = [(j, t) for j in J for t in TIPOS if Y[j, t].X > 0.5]

                # Cálculos
                total_burritos = sum(Z[i, j].X for i in I for j in J if (i, j) in a and X[i, j].X > 0.5)
                faturacao = total_burritos * r
                custo_ingredientes = total_burritos * k_ing
                custo_frota = sum(CUSTO_FIXO[t] for j, t in opened_trucks)
                custo_mkt_gasto = sum(M[i].X * custo_campanha for i in I)
                lucro_liquido = faturacao - custo_ingredientes - custo_frota - custo_mkt_gasto

                # Dash
                st.subheader("📊 Resumo Financeiro da Operação")
                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("Faturação", f"{faturacao:,.2f} €")
                col2.metric("Matéria Prima", f"- {custo_ingredientes:,.2f} €")
                col3.metric("Frota", f"- {custo_frota:,.2f} €")
                col4.metric("Marketing", f"- {custo_mkt_gasto:,.2f} €")
                col5.metric("Lucro Líquido", f"{lucro_liquido:,.2f} €")
                st.markdown("---")

                # Gráfico
                st.subheader("🗺️ Mapa Logístico da Operação")
                fig, ax = plt.subplots(figsize=(10, 6))
                ax.scatter(df_demand['x'], df_demand['y'], c='gray', s=30, label='Edifícios', alpha=0.5, zorder=2)

                for j, tipo in opened_trucks:
                    t_row = df_truck[df_truck['index'] == j].iloc[0]
                    ax.scatter(t_row['x'], t_row['y'], c=CORES_TAMANHO[tipo], marker='s', s=SIZES_GRAFICO[tipo], edgecolor='black', zorder=3, label=f'Camião {tipo}' if f'Camião {tipo}' not in ax.get_legend_handles_labels()[1] else "")
                    ax.text(t_row['x'], t_row['y'] + 10, f"{j}\n({tipo})", color='black', fontweight='bold', ha='center', fontsize=8)

                for i in I:
                    if M[i].X > 0.5:
                        d_row = df_demand[df_demand['index'] == i].iloc[0]
                        ax.scatter(d_row['x'], d_row['y'], c='gold', marker='*', s=200, edgecolor='black', zorder=4, label='Marketing Ativo' if 'Marketing Ativo' not in ax.get_legend_handles_labels()[1] else "")
                    for j in J:
                        if (i, j) in a and X[i, j].X > 0.5:
                            d_row = df_demand[df_demand['index'] == i].iloc[0]
                            t_row = df_truck[df_truck['index'] == j].iloc[0]
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
                for i in I:
                    if M[i].X > 0.5:
                        camps = int(M[i].X)
                        base_demand = next(a[i, j] for j in J if (i, j) in a)
                        mkt_data.append({"Edifício": i, "Campanhas": camps, "Procura Base": int(base_demand), "Nova Procura": int(base_demand + (camps * aumento_pct * base_demand)), "Custo (€)": camps * custo_campanha})
                if len(mkt_data) > 0:
                    st.dataframe(pd.DataFrame(mkt_data), use_container_width=True, hide_index=True)
                else:
                    st.info("Nenhuma campanha considerada rentável.")

                col_tab1, col_tab2 = st.columns(2)
                with col_tab1:
                    st.subheader("🚚 Frota Instalada")
                    st.dataframe(pd.DataFrame([{"Camião": j, "Tipo": t, "Cap.": CAPACIDADE[t], "Vendas": int(sum(Z[i, j].X for i in I if (i, j) in a and X[i, j].X > 0.5)), "Custo (€)": CUSTO_FIXO[t]} for j, t in opened_trucks]), use_container_width=True, hide_index=True)
                with col_tab2:
                    st.subheader("🏢 Alocação de Edifícios")
                    st.dataframe(pd.DataFrame([{"Edifício": i, "Camião": j, "Tipo": next(t for t in TIPOS if Y[j, t].X > 0.5), "Burritos": int(Z[i, j].X)} for i in I for j in J if (i, j) in a and X[i, j].X > 0.5]), use_container_width=True, hide_index=True)

            elif model.Status == GRB.INFEASIBLE:
                st.error("❌ O Modelo é Inviável!")
else:
    st.info("👆 Por favor, carregue o ficheiro Excel com os dados do 'Burrito Game' para desbloquear o simulador.")
