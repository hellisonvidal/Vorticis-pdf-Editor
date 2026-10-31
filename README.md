<p align="center"><img src="vorticis_pdf/resources/logo.png" width="150" alt="Vorticis PDF Editor"></p>

<h1 align="center">Vorticis PDF Editor</h1>

<p align="center">Visualizador, editor e conversor de PDF <b>gratuito</b> para Windows. É prático e rápido.</p>

---

## Download

Na aba **[Releases](../../releases)** há dois arquivos separados:

| Arquivo | O que é |
|---|---|
| **`VorticisPDF-Instalador-x.y.z.exe`** | Instalador. Cria atalhos e pode adicionar o menu do botão direito. **Não pede senha de administrador**, porque instala para o usuário atual. |
| **`VorticisPDF-Portatil-x.y.z.zip`** | Versão portátil, sem instalação. Descompacte e execute `VorticisPDF.exe`. Funciona até de um pendrive, e configurações, histórico e logs ficam na pasta `dados`, ao lado do programa. |

Requer Windows 10 ou 11 (64 bits). Nenhuma outra instalação é necessária, porque o Python e as bibliotecas já vão embutidos.

O build automático testa cada versão num Windows limpo antes de publicá-la. O teste instala sem administrador, executa o autoteste (`VorticisPDF.exe --selftest`, que abre, edita, une, separa e converte), confere o menu do botão direito e desinstala. A versão portátil passa pelo mesmo autoteste.

> **"O Windows protegeu o computador" (SmartScreen):** esse aviso aparece para qualquer programa novo sem certificado digital pago. Ele não indica problema no arquivo. Clique em **Mais informações › Executar assim mesmo**. Para conferir a integridade dos downloads, use o `SHA256SUMS.txt` publicado junto com cada versão. Projetos de código aberto podem obter assinatura gratuita pelo [SignPath Foundation](https://signpath.org), o que remove o aviso.

## Funcionalidades

### Visualizar
* Rolagem contínua das páginas. Só as páginas visíveis são renderizadas, então mesmo arquivos grandes abrem rápido.
* Zoom por `Ctrl` + roda do mouse, `Ctrl` `+` / `-`, ajuste à largura ou página inteira, além de 25 % a 400 %.
* Painel de **miniaturas** com tamanho ajustável (controle deslizante ou `Ctrl` + roda) e **visualização ampliada** de qualquer página (barra de espaço ou duplo clique).
* Busca de texto (`Ctrl+F`), seleção e cópia de texto.

### Editar
| Ferramenta | Atalho | O que faz |
|---|---|---|
| Editar texto | `E` | Passe o mouse sobre um texto para ver a fonte na barra de status e clique para editá-lo. **A fonte original é reconhecida e mantida** (veja abaixo) |
| Adicionar texto | `T` | Insere texto em qualquer ponto, com qualquer fonte instalada |
| Destacar | `M` | Marca-texto sobre as palavras |
| Retângulo | `R` | Desenha um retângulo |
| Apagar área | `W` | Remove definitivamente o conteúdo da área (redação) |
| Nota | `N` | Comentário (post-it) |
| Imagem | `I` | Insere uma imagem (assinatura, logotipo…) |
| Recortar | `C` | Recorta a área visível de uma página ou de todas |

Para desfazer e refazer use `Ctrl+Z` / `Ctrl+Y`. Os 20 últimos passos ficam guardados.

### Reconhecimento automático de fontes
Ao editar um texto, o programa procura a fonte nesta ordem:
1. a **fonte embutida no próprio PDF**, se tiver todos os caracteres necessários;
2. a **mesma fonte instalada no Windows**, comparando nome PostScript, nome completo e família + estilo (`ABCDEF+Arial-BoldMT` é reconhecida como *Arial Bold*);
3. uma **fonte equivalente**, como Arial ↔ Liberation Sans, Calibri ↔ Carlito ou Times ↔ Liberation Serif;
4. as **fontes padrão do PDF** (Helvetica, Times, Courier), mantendo negrito, itálico, serifa e monoespaçamento.

O editor de texto mostra a fonte detectada: nome, estilo, tamanho, cor, tipo e se está embutida. Também mostra a fonte que será usada e uma **prévia ao vivo nessa fonte**. Se algum caractere digitado não existir na fonte embutida (PDFs costumam embutir só os caracteres usados), o programa avisa e usa a mesma fonte instalada no computador.

**O texto digitado não sobrescreve linhas e marcações:**
* só os caracteres do trecho editado são removidos, e as linhas de texto vizinhas, bordas de tabela, sublinhados, retângulos e imagens permanecem intactos;
* se o novo texto for maior que o espaço disponível (até o próximo texto, borda de célula, linha vertical ou margem), o tamanho da fonte é ajustado automaticamente para caber. Essa opção pode ser desligada;
* ao adicionar texto num ponto já ocupado, o programa avisa antes de inserir.

Todas as fontes instaladas entram na lista: `C:\Windows\Fonts`, as fontes do usuário e qualquer arquivo copiado para `%APPDATA%\Vorticis PDF Editor\fonts`. Também entram as 14 fontes padrão do PDF e as fontes CJK. A janela de edição mostra a fonte original e a fonte reconhecida, e você pode escolher outra. Em **Arquivo › Propriedades e fontes** aparece a lista das fontes do documento com a fonte correspondente no sistema.

### Organizar páginas
* **Modo Organizar** (`F6`): miniaturas grandes em grade. Arraste para reordenar, use `Shift`/`Ctrl` para selecionar várias páginas e solte arquivos de fora para inseri-los na posição exata.
* **Botão direito** sobre as miniaturas: girar, mover para o início ou o fim, duplicar, inserir página em branco, inserir arquivo, extrair para novo PDF, separar aqui, imprimir seleção, inverter ordem, selecionar páginas pares ou ímpares, excluir.

### Unir, separar e imprimir
* **Unir**: aceita PDFs, Word, Excel, PowerPoint, imagens e outros formatos, que são convertidos automaticamente. Arraste para definir a ordem e use **Adicionar pasta** para incluir todos os arquivos de uma pasta. Cada arquivo vira um marcador no PDF final.
* **Separar**: uma página por arquivo, a cada N páginas, por intervalos (`1-3, 4, 5-`) ou ao meio. Funciona com vários PDFs de uma vez.
* **Imprimir** (`Ctrl+P`): imprime na ordem atual das páginas, com pré-visualização. Páginas em paisagem giram automaticamente.

### Converter
| De → Para | Como |
|---|---|
| Imagens (PNG, JPG, TIFF, BMP, GIF, WEBP), XPS, EPUB, CBZ, FB2, SVG, TXT → PDF | Nativo |
| Word, Excel, PowerPoint, ODF, RTF, CSV, HTML → PDF | Pelo **LibreOffice** (gratuito) ou pelo **Microsoft Office**, se estiver instalado. Sem nenhum dos dois, faz uma conversão simplificada de DOCX, XLSX, CSV e HTML |
| PDF → Word (.docx) | Mantém o layout (pdf2docx) |
| PDF → Excel (.xlsx) | Uma planilha por página. Tabelas são detectadas, e as colunas são montadas a partir das linhas de texto |
| PDF → PowerPoint (.pptx) | Um slide por página, com o texto nas notas |
| PDF → PNG / JPG / TIFF, TXT, HTML, Markdown, ODT, PDF otimizado | Nativo |

### Menu do botão direito no Windows Explorer
Ative pelo instalador ou em **Ferramentas › Adicionar ao menu do botão direito**. Não exige administrador. Depois disso, selecione os arquivos numa pasta, clique com o botão direito e escolha **Vorticis PDF**:

* **PDF**: Abrir · **Unir PDFs selecionados** · **Separar PDF** · **Organizar páginas** · Imprimir · Converter PDF para…
* **Office e imagens**: Converter para PDF · Unir como um único PDF · Abrir

Se vários arquivos estiverem selecionados, o Vorticis junta todos numa única operação. Também são criados atalhos em **Enviar para** (*Vorticis - Unir em PDF* e *Vorticis - Organizar páginas*).
> No Windows 11, as opções ficam em **"Mostrar mais opções"** (ou `Shift+F10`).

### Informações de salvamento
* Depois de salvar, uma janela mostra o arquivo, a data e a hora, o número de páginas, o tamanho antes e depois, a proteção por senha e a **lista de alterações feitas**.
* A barra de status indica quantas alterações ainda não foram salvas. Ao fechar, o programa pergunta se quer salvar e lista as alterações.
* Os metadados do PDF são atualizados: data de modificação e produtor *Vorticis PDF Editor*.
* **Arquivo › Histórico de salvamentos** guarda todos os salvamentos, uniões e separações. O histórico fica em `%APPDATA%\Vorticis PDF Editor\historico_salvamentos.jsonl`.
* O salvamento é atômico: o arquivo é gravado num temporário e depois substituído, então uma falha não corrompe o original. As fontes são subconjuntadas para gerar arquivos menores.
* Opcionalmente, o PDF pode ser protegido com senha (AES-256) em **Propriedades › Segurança**.

### Linha de comando
```
VorticisPDF.exe arquivo.pdf
VorticisPDF.exe --merge a.pdf b.pdf planilha.xlsx
VorticisPDF.exe --split a.pdf
VorticisPDF.exe --organize a.pdf b.pdf
VorticisPDF.exe --print a.pdf
VorticisPDF.exe --convert a.pdf          (PDF → Word/Excel/...)
VorticisPDF.exe --to-pdf documento.docx  (Office/imagens → PDF)
VorticisPDF.exe --register-shell | --unregister-shell
```

### Diagnóstico de erros
Se algo der errado, o programa mostra uma mensagem e continua aberto. Os detalhes, inclusive falhas internas, ficam em **Ajuda › Abrir registro de erros** (`vorticis_erros.log`).

## Compilar a partir do código-fonte

Requer Python 3.10 ou superior no Windows:

```bat
build_windows.bat
```

O script gera `dist\VorticisPDF\VorticisPDF.exe`. Se o [Inno Setup](https://jrsoftware.org/isinfo.php) estiver instalado, também gera o instalador em `installer\Output\`.

Para rodar sem compilar:

```bat
pip install -r requirements.txt
python vorticis.py
```

O ícone pode ser gerado de novo com `python tools/make_icon.py`.

### Estrutura
```
vorticis_pdf/
  app.py               entrada, linha de comando, instância única
  main_window.py       janela principal, barras de ferramentas e menus
  viewer.py            visualizador com zoom e ferramentas de edição
  thumbnails.py        miniaturas (arrastar, menu do botão direito, zoom)
  document.py          operações de PDF, desfazer/refazer, salvamento, unir/separar
  fonts.py             catálogo de fontes e reconhecimento automático
  converters.py        conversões entre formatos
  dialogs.py           diálogos (texto, unir, separar, converter, salvamento, propriedades)
  printing.py          impressão com pré-visualização
  shell_integration.py menu de contexto do Explorer (HKCU)
  single_instance.py   agrupa os arquivos selecionados no Explorer
```

## Licença
GNU AGPL-3.0, a mesma licença do PyMuPDF, que é a base do programa. É software livre e gratuito.
