# ETF Tokenizado — MVP de Tokenized Ownership com Vyper + Oracle Off-chain

Este repositório implementa um **MVP conceitual de um ETF tokenizado on-chain**, inspirado no funcionamento do **mercado primário de ETFs tradicionais**, mas adaptado para o contexto de **Tokenized Ownership**.

O projeto demonstra como um ETF poderia existir **inteiramente na blockchain**, tendo:

- **Ativos tokenizados** (simulados via ERC-20 mock)
- **Um oráculo próprio**, controlado pelo emissor, que alimenta preços de ativos
- **Integração off-chain** com dados de mercado reais (Yahoo Finance)
- **Um contrato ETF** que usa esses preços para calcular o valor da cota on-chain

A implementação tem propósito **didático**, servindo como estudo sobre:
- arquitetura mínima de smart contracts,
- fluxo off-chain → on-chain,
- tokenização de ativos financeiros,
- e separação entre *oráculo*, *ativos subjacentes* e *contrato agregador*.

Este MVP **não replica um ETF real**, mas mostra de forma clara as peças essenciais que apareceriam em uma arquitetura profissional.

---

# Arquitetura Geral

## 1. `tokenmock.vy`
Token ERC-20 simples usado para simular ações da cesta do ETF.  
Via Remix, você faz deploy de múltiplos tokens — por exemplo AAPL, TSLA, MSFT — e usa seus endereços no ETF.

## 2. `oracle.vy`
Contrato oráculo que armazena preços enviados por um feed externo.

- Cada preço é armazenado como:
  - `symbol: bytes32` (ex.: b"AAPL")
  - `price: uint256` escalado por `PRICE_SCALE`
  - `timestamp: uint256`
- Não faz nenhum cálculo.  
- Apenas guarda e fornece dados.

## 3. `oracle_updater.py`
Script responsável por:

- Buscar preços reais no Yahoo Finance (via yfinance)
- Converter para `bytes32`
- Escalar o preço
- Assinar transações com uma chave privada
- Enviar para `oracle.setPrice(...)`

Código citado:  
:contentReference[oaicite:0]{index=0}

## 4. `ETF.vy`
Contrato principal do ETF:

- Guarda:
  - Endereços dos 3 tokens da cesta
  - Símbolos usados pelo oráculo
  - Endereço do próprio oráculo
- Lê os preços em tempo real do oráculo
- Calcula o **valor da cota** com base nos preços e nas quantidades simuladas
- (MVP) Não implementa criação/destruição real de cotas, nem mint/redeem.  
  É focado apenas em demonstrar **como o ETF leria preços on-chain**.

---

# Fluxo para executar a demo

### **1. Iniciar o nó local Hardhat**
```bash
npx hardhat node
```

Isso fornece contas locais com ETH infinito e um RPC para o Remix se conectar.

---

### **2. Conectar o Remix ao Hardhat**
No Remix:

- Ative **Deploy & Run**
- Em *Environment*, escolha **Dev Provider → Hardhat**
- RPC: `http://127.0.0.1:8545`

---

### **3. Fazer deploy dos TokenMock (3 unidades)**
Para cada token:

1. Abra o arquivo `tokenmock.vy`
2. Compile
3. Deploy
4. Copie o endereço do token

---

### **4. Fazer deploy do Oráculo**
1. Abra `oracle.vy`
2. Compile
3. Deploy
4. Copie o endereço do oráculo  
   (será usado pelo script Python)

---

### **5. Rodar o script Python que atualiza preços**
Criar `.env` como:

```
RPC_URL=http://127.0.0.1:8545
ORACLE_ADDRESS=0xSEU_ORACLE
UPDATER_PRIVATE_KEY=0xSUA_CHAVE
TICKERS=AAPL,TSLA,MSFT
PRICE_SCALE=100000000
CHAIN_ID=31337
```

Executar:

```bash
python scripts/oracle_updater.py --watch --interval 10
```

O script começa a enviar preços reais para o oráculo automaticamente.

---

### **6. Fazer deploy do ETF**
1. Abra `ETF.vy` no Remix
2. Insira:
   - Os **3 endereços dos tokens**
   - Os **3 símbolos bytes32** (ex.: `"AAPL"`, `"TSLA"`, `"MSFT"`)
   - O **endereço do oráculo**
3. Deploy

Agora o ETF já consegue:
- Ler preços do oráculo
- Calcular valor agregado
- Reportar o valor da cota com precisão on-chain


