# pimlint

Validador de feeds de produto por canal. Lê um CSV de produtos, compara com o
schema do canal (atributos obrigatórios, tipos, enums, limites de tamanho,
padrões) e reporta cada violação com **linha, coluna e motivo**, ordenada por
severidade. Também calcula o **completeness score** do arquivo.

Feito para o trabalho de PIM: o objetivo é reduzir o retrabalho manual e o tempo
de triagem de um feed rejeitado, não ser um framework.

## Por que existe

Um feed rejeitado por um marketplace custa tempo de engenharia até alguém
descobrir *qual* atributo, *qual* linha, *qual* valor. Este tool transforma isso
em uma lista de erros acionável, com código de saída não-zero para CI.

## Uso

```bash
pip install -r requirements.txt

python -m pimlint --list-channels
python -m pimlint products.csv --channel amazon
python -m pimlint products.csv --channel shopify --format json -o relatorio.json
python -m pimlint products.csv --channel amazon --all
```

Códigos de saída:

| código | significado |
|--------|-------------|
| 0 | sem findings no nível de `--fail-on` |
| 1 | há findings no nível ou acima de `--fail-on` (padrão: `error`) |
| 2 | erro de uso (canal desconhecido, arquivo ausente, schema não encontrado) |

Níveis de `--fail-on`: `critical`, `error`, `warning`, `never`.

## Schemas

Um YAML por canal em `schemas/`. Cada atributo pode declarar:

```yaml
title:
  type: string        # string | int | float | bool | date | enum
  required: true
  min_length: 3
  max_length: 255
  pattern: "^https?://.+"
  severity: error     # critical | error | warning (padrão: error)
  values: [BRL, USD]  # obrigatório quando type=enum
```

Atalho: `sku: required` equivale a `sku: {required: true}`.

## Severidades

- `critical` — impede o envio ao canal (atributo obrigatório ausente)
- `error` — rejeita o produto ou causa reprocessamento (tipo, enum, padrão, tamanho)
- `warning` — aceito pelo canal, mas viola guideline

O relatório sai ordenado por severidade e, dentro dela, por linha.

## Exemplo de saída

```
canal: amazon
linhas: 10
completeness: 96.67%
erros: 3 critical, 3 error, 0 warning

  linha     4  CRITICAL  brand: atributo obrigatório ausente: brand
  linha     4  CRITICAL  image_main: atributo obrigatório ausente: image_main
  linha     6  CRITICAL  title: atributo obrigatório ausente: title
  linha     5  ERROR     price: esperado número decimal, encontrado 'many'
  linha     5  ERROR     image_main: não casa com o padrão esperado: ^https?://.+
  linha     7  ERROR     condition: 'usado' fora dos valores permitidos: new, used, refurbished, collectible
```

O mesmo arquivo pode passar em um canal e reprovar em outro — é o comportamento
esperado, e o motivo está no schema, não no código.

## Desenvolvimento

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest
```

`samples/products.csv` tem erros propositais (campo obrigatório vazio, `price`
não numérico, URL com esquema inválido, enum fora do dominio, valor de estoque
negativo) para exercitar cada regra.

## Relatório HTML

`--format html` produz um documento único, sem dependências externas, com:

- **Indicadores no topo** — completeness score com barra e linha de referência,
  produtos reprovados, total de violações, produtos aprovados
- **Atributos que mais reprovam** — ordenado por ocorrência, com a severidade
  mais grave de cada coluna. É a ordem de ataque: o primeiro item dessa lista
  destrava mais linhas do que os dez seguintes juntos
- **Reprovação por produto** — cada linha do CSV com quantos obrigatórios foram
  preenchidos
- **Violações** — tabela completa, filtrável por texto e severidade, com o valor
  encontrado exibido
- **Colunas fora do schema** — o que existe no CSV e não está no schema

Exemplo gerado: [`samples/report_amazon.html`](samples/report_amazon.html)

## Estado atual

Funcionando: schema loader, validação de tipo/presença/tamanho/padrão/enum,
completeness score, ordenação por severidade, saídas em texto, JSON e HTML,
códigos de saída para CI, detecção de colunas fora do schema, tratamento de
BOM/CRLF, relatório HTML com filtros, GitHub Actions com artifacts do relatório.

Falta: validação de arquivos de mapping, comparação de dois arquivos (feed antes
× depois da correção), e schema de canal carregado de fonte externa em vez de
versionado no repo.
