import cv2
import pandas as pd
import tkinter as tk
from tkinter import filedialog
import streamlit as st
import os
import plotly.express as px
import re 
# Importações de Web Scraping e Navegador
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

# --- Configurações Iniciais ---
st.set_page_config(page_title="Análise Fiscal BI", layout="wide")


arquivo_csv_chaves = "chaves_qrcode.csv"
CSV_FILE = 'dados_vendas.csv' # Arquivo principal de dados de vendas



# --- Funções de Manipulação de Dados ---

def get_base_data():
    
    cols = ['DataHora', 'Produto', 'Quantidade', 'PrecoUnitario', 'TotalVenda', 'FormaPagamento', 'Data']
    
    if os.path.exists(CSV_FILE):
        try:
            df = pd.read_csv(CSV_FILE)
            
            # Garantir que os tipos de dados estão corretos
            df['DataHora'] = pd.to_datetime(df['DataHora'])
            df['Data'] = df['DataHora'].dt.date 
            
            # Limpeza (remove linhas sem produto)
            df = df.dropna(subset=['Produto'])
            
            df.sort_values(by='DataHora', ascending=False, inplace=True)
            return df
        except pd.errors.EmptyDataError:
            st.info(f"O arquivo '{CSV_FILE}' existe, mas está vazio.")
            return pd.DataFrame({c: [] for c in cols})
    else:
        st.info(f"Arquivo de dados '{CSV_FILE}' não encontrado. Use a Fase 1 para coletar dados.")
        return pd.DataFrame({c: [] for c in cols})

def save_data(df):
    """Salva o DataFrame no arquivo CSV."""
    df.to_csv(CSV_FILE, index=False)


# --- Funções de Raspagem (Web Scraping) ---

def limpar_valor(texto):
    """Remove caracteres não numéricos e converte para float."""
    limpo = re.sub(r'[^\d,\.]', '', texto)
    limpo = limpo.replace(',', '.')
    match = re.search(r'(\d+\.?\d*)', limpo)
    return float(match.group(1)) if match else 0.0

def extrair_dados_do_cupom(chave_acesso, url_base="https://www.nfce.se.gov.br/portal/consultarNfce.jsp?p="):
    """
    Tenta raspar os dados de itens de venda da URL do cupom fiscal.
    Inclui lógica para IFRAME.
    """
    
    st.markdown("---")
    st.subheader("Processando Dados do Cupom (Web Scraping)...")

    try:
        # Configuração do Selenium
        service = Service(ChromeDriverManager().install())
        options = webdriver.ChromeOptions()
        options.add_argument('--headless') 
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        
        driver = webdriver.Chrome(service=service, options=options)
        url_completa = f"{url_base}{chave_acesso}"
        st.info(f"🌐 Tentando acessar URL: {url_completa}")
        driver.get(url_completa)
        time.sleep(5) 

        dados_vendas = []
        data_hora_venda = ()
        forma_pagamento = "Não Capturado"

        # --- PASSO 1: Mudar o Foco para o IFRAME ---
        try:
            # Tenta localizar o iframe
            iframe = driver.find_element(By.XPATH, "//iframe[contains(@src, 'nfce')]") 
            driver.switch_to.frame(iframe)
            st.success("✅ Foco do Selenium alterado para o IFRAME do Cupom Fiscal.")
            time.sleep(2) 
        except Exception:
            st.warning("⚠️ Não foi possível encontrar o IFRAME. Tentando raspar no contexto principal.")

        # --- PASSO 2: Capturar Data/Hora e Forma de Pagamento (Geral) ---
        try:
            # XPATH Comum para data/hora
            data_hora_txt = driver.find_element(By.XPATH, "//*[contains(text(), 'Emissão:')]/following-sibling::*").text
            match = re.search(r'(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})', data_hora_txt)
            if match:
                 data_hora_venda = (match.group(1), '%d/%m/%Y %H:%M:%S')

            # XPATH Comum para Forma de Pagamento
            forma_pag_element = driver.find_element(By.XPATH, "//*[contains(text(), 'Forma de Pagamento')]/following-sibling::*")
            forma_pagamento = forma_pag_element.text.strip()
        except:
            st.warning("Não foi possível capturar Data/Hora ou Forma de Pagamento.")

        # --- PASSO 3: Extração dos Itens de Venda (Produtos) ---
        try:
            # ⚠️ XPATH MAIS COMUM PARA TABELA DE ITENS (Ajustar aqui se o layout do seu estado for diferente):
            tabela_itens = driver.find_element(By.XPATH, "//table[@class='tabelaItens']")
            
            linhas = tabela_itens.find_elements(By.TAG_NAME, "tr")[1:] # Pula o cabeçalho
            
            for linha in linhas:
                colunas = linha.find_elements(By.TAG_NAME, "td")
                
                # Mapeamento de Colunas Padrão NFCE:
                # 0: Produto | 2: Quantidade | 4: Preço Unitário | 5: Valor Total
                
                if len(colunas) >= 6: 
                    produto = colunas[0].text.strip()
                    quantidade = limpar_valor(colunas[2].text) 
                    preco_unitario = limpar_valor(colunas[4].text)
                    total_venda_item = limpar_valor(colunas[5].text)
                    
                    dados_vendas.append({
                        'Produto': produto,
                        'Quantidade': quantidade,
                        'PrecoUnitario': preco_unitario,
                        'TotalVenda': total_venda_item,
                        'DataHora': data_hora_venda,
                        'FormaPagamento': forma_pagamento,
                        'Data': data_hora_venda.date()
                    })

            if not dados_vendas:
                st.error("Nenhum item de venda encontrado. XPATH da tabela ou índices podem estar incorretos.")
                return None 
                
        except Exception as e:
            st.error(f"❌ Erro na raspagem da tabela de itens: {e}")
            return None 
            
        # 4. Salvar Dados
        if dados_vendas:
            df_novas_vendas = pd.DataFrame(dados_vendas)
            st.session_state.df = pd.concat([df_novas_vendas, st.session_state.df], ignore_index=True)
            save_data(st.session_state.df)
            
            st.success(f"✅ Dados de **{len(dados_vendas)} itens** extraídos e salvos com sucesso!")
            
    except Exception as e:
        st.error(f"❌ Erro geral no Web Scraping: {e}")
    finally:
        if 'driver' in locals():
            try:
                driver.quit()
            except:
                pass
            
def extrair_chave(qr_data):
    """Extrai a chave de acesso da URL do QR Code (formato p=chave|... )."""
    if "?" in qr_data and "p=" in qr_data:
        parte = qr_data.split("p=")[1]
        chave = parte.split("|")[0]
        return chave.strip()
    return None

def salvar_chave(chave):
    """Salva a chave em um CSV e chama a raspagem de dados."""
    # ... (lógica de verificação da chave omitida para brevidade, mas está no código) ...
    if os.path.exists(arquivo_csv_chaves):
        df = pd.read_csv(arquivo_csv_chaves)
        if chave not in df['ChaveAcesso'].values:
            novo_df = pd.DataFrame({"ChaveAcesso": [chave]})
            df = pd.concat([df, novo_df], ignore_index=True)
            df.to_csv(arquivo_csv_chaves, index=False, encoding="utf-8")
            st.success("✅ Chave salva com sucesso.")
        else:
            st.warning("⚠️ Cupom já lido. Tentando apenas extrair dados novamente.")
    else:
        df = pd.DataFrame({"ChaveAcesso": [chave]})
        df.to_csv(arquivo_csv_chaves, index=False, encoding="utf-8")
        st.success("✅ Chave salva com sucesso.")
        
    extrair_dados_do_cupom(chave)

def ler_qr_imagem():
    arquivo = st.file_uploader("Selecione uma imagem de QR Code", type=["png", "jpg", "jpeg", "bmp"])

    if arquivo is not None:
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(arquivo.read()))
        st.image(img, caption="QR carregado")

        # Detectar texto do QR
        try:
            import cv2
            import numpy as np
            detector = cv2.QRCodeDetector()
            img_cv = cv2.imdecode(np.frombuffer(arquivo.getvalue(), np.uint8), cv2.IMREAD_COLOR)
            dados, _, _ = detector.detectAndDecode(img_cv)

            if dados:
                chave = extrair_chave(dados)
                if chave:
                    salvar_chave(chave)
                else:
                    st.error("QR lido, mas chave não encontrada.")
            else:
                st.error("Nenhum QR Code detectado.")
        except:
            st.error("Erro ao ler QR Code.")


def ler_qr_camera():
    cap = cv2.VideoCapture(0)
    detector = cv2.QRCodeDetector()
    st.info("📷 Leitor de QR Code iniciado. Pressione 'q' para sair da janela.")
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        data, bbox, _ = detector.detectAndDecode(frame)
        if bbox is not None:
            bbox = bbox.astype(int)
            for i in range(len(bbox)):
                pt1 = tuple(bbox[i][0])
                pt2 = tuple(bbox[(i + 1) % len(bbox)][0])
                cv2.line(frame, pt1, pt2, (0, 255, 0), 3)
            if data:
                chave = extrair_chave(data)
                if chave:
                    print("QR Code detectado:", chave)
                    salvar_chave(chave)
                    (data)
        cv2.imshow("Leitor de QR Code", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()

# --- LAYOUT PRINCIPAL DO STREAMLIT ---

# Carregar dados
df_vendas = get_base_data()
if 'df' not in st.session_state or st.session_state.df.empty:
    st.session_state.df = df_vendas

st.title("📊 Análise Fiscal BI: Coleta e Visualização Automatizada")

aba = st.sidebar.radio("Escolha a Fase da Aplicação:", ["Fase 1 — Coleta de Dados Fiscais", "Fase 2 — Dashboard de Análise"])

# --- Interface FASE 1: Coleta e Raspagem ---
if aba.startswith("Fase 1"):
    st.header("🧾 Coletor de Dados de Cupom Fiscal (QR Code)")
    st.markdown("Use esta fase para ler o QR Code. A chave será extraída, e os dados da venda serão **automaticamente** coletados via Web Scraping e armazenados.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📂 Ler QR Code de Imagem"):
            ler_qr_imagem()
    with col2:
        if st.button("📸 Ler QR Code pela Câmera"):
            ler_qr_camera()

    if os.path.exists(arquivo_csv_chaves):
        df_chaves = pd.read_csv(arquivo_csv_chaves)
        st.markdown("### 🔑 Chaves Fiscais Lidas:")
        st.dataframe(df_chaves, use_container_width=True)

# --- Interface FASE 2: Dashboard de Análise ---
else: 
    df = st.session_state.df.copy()

    st.title("💰 Dashboard de Análise de Vendas")
    
    if df.empty:
        st.warning("Nenhum dado de vendas disponível. Por favor, leia um QR Code na Fase 1 para iniciar a coleta.")
    else:
        # --- Filtros de Dados ---
        st.subheader("Filtros de Dados")
        col1, col2, col3 = st.columns(3)

        # 1. FILTRO DE PERÍODO (DATA)
        min_date = df['Data'].min()
        max_date = df['Data'].max()
        
        data_inicio = col1.date_input("Data de Início:", min_date)
        data_fim = col1.date_input("Data de Fim:", max_date)
        
        # Filtrar o DataFrame pelo período
        df_filtrado = df[(df['Data'] >= data_inicio) & (df['Data'] <= data_fim)].copy()
        
      # 2. FILTRO POR PRODUTO
        produtos_unicos = ['Todos'] + sorted(df['Produto'].unique().tolist())
        produto_selecionado = col2.selectbox("Produto:", produtos_unicos)
        if produto_selecionado != 'Todos':
            df_filtrado = df_filtrado[df_filtrado['Produto'] == produto_selecionado]



        # 3. FILTRO POR FORMA DE PAGAMENTO
        formas_pagamento_unicas = ['Todas'] + sorted(df['FormaPagamento'].unique().tolist())
        pagamento_selecionado = col3.selectbox("Forma de Pagamento:", formas_pagamento_unicas)
        
        if pagamento_selecionado != 'Todas':
            df_filtrado = df_filtrado[df_filtrado['FormaPagamento'] == pagamento_selecionado]

        st.markdown("---")

        # --- Visualizações e Métricas ---

        if df_filtrado.empty:
            st.warning("Nenhum dado encontrado com os filtros selecionados.")
        else:
            # Cálculo de Métricas (Total de vendas, Valor médio por venda)
            valor_medio_venda = df_filtrado['TotalVenda'].sum() / df_filtrado['DataHora'].nunique() if df_filtrado['DataHora'].nunique() > 0 else 0
            total_vendas_geral = df_filtrado['TotalVenda'].sum()
            
            col_tv, col_transacoes, col_vm = st.columns(3)
            col_tv.metric("Total de Vendas (R$)", f"R$ {total_vendas_geral:,.2f}")
            col_transacoes.metric("Nº de Transações (Cupons)", df_filtrado['DataHora'].nunique())
            col_vm.metric("Valor Médio por Venda (R$)", f"R$ {valor_medio_venda:,.2f}")
            
            st.markdown("### Gráficos de Análise")
            
            tab1, tab2 = st.tabs(["Tendência e Produtos", "Formas de Pagamento e Tabela"])

            with tab1:
                # Total de vendas por dia/semana/mês
                st.subheader("Total de Vendas por Período")
                
                opcao_tempo = st.radio(
                    "Agrupar por:",
                    ('Dia', 'Semana', 'Mês'),
                    horizontal=True,
                    key='tend_group'
                )
                
                # Lógica de agrupamento por período
                df_agrupado = df_filtrado.set_index('DataHora').resample('D')['TotalVenda'].sum().reset_index()
                x_label = 'Dia'
                if opcao_tempo == 'Semana':
                    df_agrupado = df_filtrado.set_index('DataHora').resample('W')['TotalVenda'].sum().reset_index()
                    df_agrupado['Período'] = df_agrupado['DataHora'].dt.to_period('W').astype(str) 
                    x_label = 'Semana'
                elif opcao_tempo == 'Mês': 
                    df_agrupado = df_filtrado.set_index('DataHora').resample('M')['TotalVenda'].sum().reset_index()
                    df_agrupado['Período'] = df_agrupado['DataHora'].dt.to_period('M').astype(str)
                    x_label = 'Mês'
                else: # Dia
                    df_agrupado.columns = ['Período', 'TotalVenda']

                fig_tendencia = px.line(
                    df_agrupado,
                    x='Período',
                    y='TotalVenda',
                    title=f'Tendência de Vendas por {x_label} (R$)',
                    markers=True
                )
                st.plotly_chart(fig_tendencia, use_container_width=True)

                # Produtos mais vendidos
                st.subheader("Top 10 Produtos Mais Vendidos")
                df_produtos = df_filtrado.groupby('Produto')['Quantidade'].sum().sort_values(ascending=False).reset_index()
                fig_produtos = px.bar(
                    df_produtos.head(10),
                    x='Quantidade',
                    y='Produto',
                    orientation='h',
                    title="Top 10 Produtos Mais Vendidos (em Quantidade)",
                    color='Quantidade'
                )
                fig_produtos.update_layout(yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig_produtos, use_container_width=True)

            with tab2:
                # Comparativo entre formas de pagamento
                st.subheader("Comparativo de Vendas por Forma de Pagamento")
                df_pagamento = df_filtrado.groupby('FormaPagamento')['TotalVenda'].sum().reset_index()
                fig_pagamento = px.pie(
                    df_pagamento,
                    values='TotalVenda',
                    names='FormaPagamento',
                    title='Total de Vendas por Forma de Pagamento (R$)',
                    hole=0.3
                )
                st.plotly_chart(fig_pagamento, use_container_width=True)
                
                # Tabela de Dados
                st.subheader("Tabela de Dados Filtrados")
                st.dataframe(
                    df_filtrado[['DataHora', 'Produto', 'Quantidade', 'PrecoUnitario', 'TotalVenda', 'FormaPagamento']],
                    column_config={
                        "DataHora": st.column_config.DatetimeColumn("Data e Hora", format="DD/MM/YYYY HH:mm"),
                        "PrecoUnitario": st.column_config.NumberColumn("Preço Unitário (R$)", format="R$ %.2f"),
                        "TotalVenda": st.column_config.NumberColumn("Total da Venda (R$)", format="R$ %.2f"),
                        "Produto": "Produto",
                        "Quantidade": "Quantidade",
                        "FormaPagamento": "Forma de Pagamento"
                    },
                    hide_index=True,
                    use_container_width=True
                )

