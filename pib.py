import streamlit as st
import pandas as pd
import plotly_express as px
import plotly as pt 
import sidrapy as sidra
import streamlit as st 

# Configuração de página 
st.set_page_config(layout="wide")

# Informação 

st.markdown("### Contas Nacionais Trimestrias (Rápida Visualização)")
st.sidebar.markdown("Desenvolvido por [Vinicius](https://www.linkedin.com/in/vinicius-limeira-565117180/)")

# Coleta do Sidra 

dados_brutos = list(
    map(
        # função com 2 argumentos que será repetida
        lambda tabela, variavel: ( # lambda argumento1, argumento2: função/expressão a ser executada
            sidra.get_table(
                table_code = tabela,
                territorial_level = "1", # alguns argumentos recebem valores padrão
                ibge_territorial_code = "all",
                variable = variavel,
                classifications = { # PIB preços mercado e componentes (óticas)
                    "11255": "90687,90691,90696,90707,93404,93405,93406,93407,93408"
                    },
                period = "all"
                )
            ),

        # códigos das tabelas (pro argumento tabela)
        ["1620", "1621", "1846", "6612", "6613"],

        # códigos da variável dentro da tabela (pro argumento variavel)
        ["583", "584", "585", "9318", "9319"]
        )
    )


# Tratamento de dados
dados = (
    pd.concat(  # empilha em uma tabela todos os DataFrames
        objs = dados_brutos,
        keys = ["num_indice", "num_indice_sa", "precos_correntes",
                "precos_constantes", "precos_constantes_sa"],
        names = ["tabela", "linha"]
        )
    .reset_index()
    .rename(columns = dados_brutos[0].iloc[0])
    # filtra na coluna Trimestre tudo que não for igual a "Trimestre" (cabeçalho)
    .query("Trimestre not in 'Trimestre'")
    .rename(
        columns = {
            "Trimestre (Código)": "data",
            "Setores e subsetores": "rubrica",
            "Valor": "valor"
            }
            )
    .filter(items = ["tabela", "data", "rubrica", "valor"], axis = "columns")
    .replace( # recodifica valores da coluna rubrica
        to_replace = {
            "rubrica": {
                "Agropecuária - total": "Agropecuária",
                "Indústria - total": "Indústria",
                "Serviços - total": "Serviços",
                "PIB a preços de mercado": "PIB",
                "Despesa de consumo das famílias": "Consumo das Famílias",
                "Despesa de consumo da administração pública": "Despesa do Governo",
                "Formação bruta de capital fixo": "FBFC",
                "Exportação de bens e serviços": "Exportação",
                "Importação de bens e serviços (-)": "Importação"
                }
                }
             )
    .assign(  # substitui o 5º caracter da coluna data por "-Q" e converte em YYYY-MM-DD
        data = lambda x: pd.to_datetime(
            x.data.str.slice_replace(start = 4, stop = 5, repl = "-Q")
            ),
        valor = lambda x: x.valor.astype(float) # converte de texto para numérico
        )
    )

taxas = (
    dados.query("tabela in ['num_indice', 'num_indice_sa']")
    .pivot(index = ["data", "rubrica"], columns = "tabela", values = "valor")
    .reset_index()
    .sort_values("data") # ordena ascedentemente pela coluna data
    )
# cria novas colunas/cálculo por grupo (rubrica) feito dentro do apply()
taxas["var_margem"] = (
    taxas.groupby("rubrica", group_keys=False)["num_indice_sa"] # agrupa os dados e aponta a coluna
    .apply(lambda x: x.pct_change(1) * 100)   # calcula a variação na coluna
)
taxas["var_interanual"] = (
    taxas.groupby("rubrica", group_keys=False)["num_indice"]
    .apply(lambda x: x.pct_change(4) * 100)
)
taxas["var_anual"] = (
    taxas.groupby("rubrica", group_keys=False)["num_indice"] # soma móvel de 4 períodos
    .apply(lambda x: (x.rolling(4).sum() / x.rolling(4).sum().shift(4) - 1) * 100)
)
taxas["ano"] = taxas["data"].dt.year
taxas["num_indice_acum"] = (
    taxas.groupby(["rubrica", "ano"], group_keys=False)["num_indice"]
    .apply(lambda x: x.cumsum()) # acumula o número índice por ano/rubrica
    )
taxas["var_acum_ano"] = (
    taxas.groupby("rubrica", group_keys=False)["num_indice_acum"]
    .apply(lambda x: x.pct_change(4) * 100)
)


# Calculando o deflator
deflator = (
    dados.query(
        "tabela in ['precos_correntes', 'precos_constantes'] and rubrica == 'PIB'"
        )
    .pivot(
        index = "data",
        columns = "tabela",
        values = "valor"
        )
    .assign(
        deflator = lambda x: x.precos_correntes / x.precos_constantes * 100,
        var_anual = lambda x: (
            x.deflator.rolling(4).sum() / x.deflator.shift(4).rolling(4).sum() - 1
            ) * 100
        )
    )


# Decomposição do PIB: carrego e crescimento no ano
decomposicao = (
    dados.query("rubrica == 'PIB' and tabela == 'precos_constantes_sa'")
    .assign(
        A = lambda x: x.valor.rolling(4).mean().shift(4),
        B = lambda x: x.valor.shift(4),
        C = lambda x: x.valor.rolling(4).mean(),
        carrego = lambda x: (x.B - x.A) / x.A * 100,
        cres_ano = lambda x: (x.C - x.B) / x.A * 100,
        total = lambda x: x.carrego + x.cres_ano
        )
    .query("data.dt.quarter == 4")
    .assign(ano = lambda x: x.data.dt.year)
    .filter(items = ["ano", "carrego", "cres_ano", "total"])
    .rename(columns = {
        "carrego": "Carrego Estatístico",
        "cres_ano": "Crescimento no Ano",
        "total": "Crescimento Anual"
        }
        )
    )

## Dividindo as colunas 

col1, col2 = st.columns(2)
col3 = st.columns(1)



# Criando o gráfico de linha do PIB com Plotly Express
fig = px.line(
    taxas.query("rubrica == 'PIB'"),  # Filtrando os dados apenas para o PIB
    x="data",  # Definindo os dados do eixo x como "data"
    y=["var_margem", "var_interanual", "var_anual", "var_acum_ano"],  # Definindo as variáveis para o eixo y
    labels={  # Definindo os rótulos dos eixos
        "data": "",
        "value": "Variação %",
        "variable": "Tipo de Variação"
    },
    facet_col="variable",  # Criando subplots para cada tipo de variação
    title="PIB: taxas de variação",  # Título do gráfico
    facet_col_wrap=2,  # Definindo o número máximo de colunas para os subplots
    width=1000,  # Largura do gráfico
    height=500,  # Altura do gráfico
)

# Atualizando o layout do gráfico
fig.update_layout(
    xaxis_title="",  # Removendo o título do eixo x
    yaxis_title="",  # Removendo o título do eixo y
    legend_title="Tipo de Variação",  # Título da legenda
    title_font_size=15,  # Tamanho da fonte do título
    title_x=0.5,  # Posicionamento horizontal do título
    title_y=0.95,  # Posicionamento vertical do título
    margin=dict(l=20, r=20, t=60, b=20),  # Margens do gráfico
    showlegend=False,  # Mostrando a legenda
)

# Exibindo o gráfico

col1.plotly_chart(fig, use_container_width=True)


# Criando o gráfico com Plotly Express
fig2 = px.line(
    deflator,
    x=deflator.index,  # Usando o índice do dataframe como eixo x
    y="var_anual",     # Usando a coluna "var_anual" como eixo y
    title="Variação Anual do Deflator",  # Título do gráfico
    labels={"var_anual": "Variação Anual"}  # Rótulo do eixo y
)

# Atualizando o layout do gráfico
fig2.update_layout(
    xaxis_title="Ano",  # Título do eixo x
    yaxis_title="Variação (%)",  # Título do eixo y
)

# Exibindo o gráfico
col2.plotly_chart(fig2, use_container_width=True)


# Criando o gráfico de barras empilhadas e linha com Plotly Express
fig3 = px.bar(
    decomposicao,
    x="ano",
    y=["Carrego Estatístico", "Crescimento no Ano"],
    title="Decomposição do PIB - Contribuição ao crescimento anual",
    labels={"value": "%", "variable": ""},
    color_discrete_sequence=["#b22200", "#282f6b"],  # Cores das barras
    barmode="relative",  # Empilhar as barras
)

# Adicionando a linha de Crescimento Anual
fig3.add_scatter(
    x=decomposicao["ano"],
    y=decomposicao["Crescimento Anual"],
    mode="lines+markers",
    name="Crescimento Anual",
    line=dict(color="black", dash="dash"),  # Cor e estilo da linha
)

# Configurando o layout do gráfico
fig3.update_layout(
    xaxis_title="Ano",
    yaxis_title="%",  # Título do eixo y
    yaxis=dict(tickformat=".1f"),  # Formato dos ticks do eixo y
    legend_title="",  # Título da legenda
    width=1000,  # Largura do gráfico
    height=500,  # Altura do gráfico
    title_x=0.5,  # Posicionamento horizontal do título
    title_y=0.95,  # Posicionamento vertical do título
    bargap=0.2,  # Espaçamento entre as barras
    margin=dict(l=50, r=50, t=50, b=50),  # Margens do gráfico
)

# Exibindo o gráfico
col3[0].plotly_chart(fig3, use_container_width=True)

