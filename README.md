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

### Selecionar texto, sem escolher ferramenta
Com **nenhuma ferramenta ativa**:
* **Clique e arraste sobre o texto** com o botão esquerdo para selecioná-lo na ordem de leitura. A seleção pode ocupar várias linhas.
* **Clique duplo** seleciona a palavra, **clique triplo** a linha, `Shift`+clique estende a seleção e `Ctrl+A` seleciona a página toda.
* Arrastar numa área **sem texto** move a página.
* O **botão direito** sobre a seleção oferece: copiar, destacar, sublinhar, riscar, traduzir ou localizar.

Para desligar uma ferramenta, clique nela de novo ou pressione `Esc`.

### Ferramenta Seleção: editar vários textos ao mesmo tempo
Ative **Seleção por retângulos** (`S`, primeiro botão da barra lateral):
* **Desenhe um ou mais retângulos** sobre os textos. Todos os textos dentro deles ficam selecionados.
* Clique num texto para incluí-lo ou retirá-lo, e clique fora dos textos para limpar a seleção. `Ctrl+A` seleciona todos os textos da página.
* **Editar textos selecionados** (botão, `Enter` ou clique duplo) abre uma caixa de edição **sobre cada texto, na própria página**, para editar todos de uma vez:
  * `Tab` passa para o próximo texto; `Enter` ou um clique fora aplica; `Esc` cancela;
  * a barra de edição tem localizar e substituir em todos e pode trocar fonte, tamanho ou cor de todos. Por padrão, cada texto mantém a sua fonte original;
  * cada texto é ajustado para não sobrepor linhas e marcações.
  * A edição inteira vira um único passo de desfazer.
* A barra da seleção também permite copiar, destacar, sublinhar e excluir os textos selecionados.

### Criar um PDF do zero
**Arquivo › Novo PDF** (`Ctrl+N`), ou **Novo PDF** na tela inicial:
* tamanhos A4, A3, A5, Carta, Ofício, Legal, cartão 10 × 15 cm ou personalizado (em mm), em retrato ou paisagem;
* de 1 a 500 páginas;
* fundo **em branco, pautado, pautado com margem, quadriculado ou pontilhado**.

Depois é só clicar na página para escrever e usar formas, imagens, desenho livre e assinatura.

### Formas
Ferramenta **Formas** (`F`) na barra lateral:
* **retângulo, elipse/círculo, linha, seta, seta dupla, triângulo, losango, estrela, visto (✓) e xis (✗)**;
* a barra de opções define a cor do contorno, o preenchimento, a espessura, a opacidade e o tracejado;
* segure `Shift` para obter quadrado ou círculo perfeito e linhas a 0°, 45° ou 90°;
* **Desenho livre** (`D`): desenhe à mão com o mouse.

Todas as formas continuam editáveis: clique para selecionar, arraste para mover, use a alça do canto para redimensionar e `Delete` para excluir. O botão direito sobre a forma muda cor, preenchimento, espessura, opacidade e tracejado. As formas são gravadas como anotações PDF padrão, então também podem ser editadas em outros leitores.

### Editar
| Ferramenta | Atalho | O que faz |
|---|---|---|
| Editar texto | `E` | Passe o mouse sobre um texto para ver a fonte na barra de status e clique para editá-lo **direto na página**, sem janela separada. **A fonte original é reconhecida e mantida** (veja abaixo). `Enter` ou um clique fora aplica, `Esc` cancela |
| Adicionar texto | `T` | Insere texto em qualquer ponto, com qualquer fonte instalada |
| Destacar | `M` | Marca-texto sobre as palavras |
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

Todas as fontes instaladas entram na lista: `C:\Windows\Fonts`, as fontes do usuário e qualquer arquivo copiado para `%APPDATA%\Vorticis PDF Editor\fonts`. Também entram as 14 fontes padrão do PDF e as fontes CJK. Durante a edição, a barra de edição (no topo) permite escolher outra fonte, o tamanho e a cor, e a barra de status mostra a fonte original e a fonte usada. Em **Arquivo › Propriedades e fontes** aparece a lista das fontes do documento com a fonte correspondente no sistema.

### Organizar páginas
* **Modo Organizar** (`F6`): miniaturas grandes em grade. Arraste para reordenar, use `Shift`/`Ctrl` para selecionar várias páginas e solte arquivos de fora para inseri-los na posição exata.
* **Botão direito** sobre as miniaturas: girar, mover para o início ou o fim, duplicar, inserir página em branco, inserir arquivo, extrair para novo PDF, separar aqui, imprimir seleção, inverter ordem, selecionar páginas pares ou ímpares, excluir.

### Unir, separar e imprimir
* **Unir**: aceita PDFs, Word, Excel, PowerPoint, imagens e outros formatos, que são convertidos automaticamente. Arraste para definir a ordem e use **Adicionar pasta** para incluir todos os arquivos de uma pasta. Cada arquivo vira um marcador no PDF final.
* **Separar**: uma página por arquivo, a cada N páginas, por intervalos (`1-3, 4, 5-`) ou ao meio. Funciona com vários PDFs de uma vez.
* **Imprimir** (`Ctrl+P`) abre uma janela de impressão **toda em português**, sem pré-visualização própria (o documento já está na tela):
  * impressora e botão **Propriedades da impressora** (as opções do driver);
  * páginas: todas, a atual, as selecionadas nas miniaturas ou um intervalo (`1-3, 5, 8-`); somente ímpares ou pares; ordem inversa;
  * cópias, agrupadas ou não;
  * orientação (automática, retrato ou paisagem), papel (A4, Carta, Ofício...), escala (ajustar à página, reduzir só as grandes, tamanho real ou personalizada) e **várias páginas por folha** (2, 4, 6, 9 ou 16);
  * colorida ou em tons de cinza, qualidade (rascunho, normal ou alta) e se as anotações saem na impressão.
  * As escolhas ficam guardadas para a próxima vez.
  * A impressão segue a ordem atual das páginas, e páginas em paisagem giram automaticamente.
  * **Sempre em uma face só.** O frente e verso é desativado mesmo que esteja marcado nas propriedades da impressora.

### Converter
| De → Para | Como |
|---|---|
| Imagens (PNG, JPG, TIFF, BMP, GIF, WEBP), XPS, EPUB, CBZ, FB2, SVG, TXT → PDF | Nativo |
| Word, Excel, PowerPoint, ODF, RTF, CSV, HTML → PDF | Pelo **LibreOffice** (gratuito) ou pelo **Microsoft Office**, se estiver instalado. Sem nenhum dos dois, faz uma conversão simplificada de DOCX, XLSX, CSV e HTML |
| PDF → Word (.docx) | Mantém o layout (pdf2docx) |
| PDF → Excel (.xlsx) | Uma planilha por página, sem perder nem misturar dados (veja abaixo) |
| PDF → PowerPoint (.pptx) | Um slide por página, com o texto nas notas |
| PDF → PNG / JPG / TIFF, TXT, HTML, Markdown, ODT, PDF otimizado | Nativo |

**Conversão para Excel:**
* **OCR completo automático** nas páginas que precisam: digitalizadas, cobertas por imagem, com tabela colada como imagem ou com texto ilegível (fontes sem mapa de caracteres). Antes do OCR, as linhas das tabelas são apagadas da imagem, porque o OCR costuma pular o texto dentro de grades.
* **Tabelas com grade**, digitais ou digitalizadas, são remontadas célula por célula. Cada palavra vai para a célula em que está, então nada passa de uma célula para outra. O cabeçalho fica em negrito, com bordas.
* **Texto em colunas sem grade**, como extratos e relatórios, é alinhado pela posição na página. Números alinhados à direita e células vazias, como Débito/Crédito, caem sempre na coluna certa.
* **Números brasileiros viram números de verdade**: `1.234,56`, `R$ 1.234,56`, `-12,5%` e `(1.234,56)` (negativo). Datas `dd/mm/aaaa` viram datas. **Códigos com zero à esquerda** (CPF, CEP, matrícula, `00123`) e números longos continuam como texto, sem perder dígitos.

### Menu do botão direito no Windows Explorer
Ative pelo instalador ou em **Ferramentas › Adicionar ao menu do botão direito**. Não exige administrador. Depois disso, selecione os arquivos numa pasta, clique com o botão direito e escolha **Vorticis PDF**:

* **PDF**: Abrir · **Unir PDFs selecionados** · **Separar PDF ▸** (uma página por arquivo, ao meio, a cada 2, 5 ou 10 páginas, ímpares e pares) · **Organizar páginas** · Imprimir · **Converter para ▸** (Word, Excel, PowerPoint, PNG, JPG, TIFF, texto, HTML, Markdown, ODT, PDF otimizado ou *Mais opções...*)
* **Office e imagens**: Converter para PDF · **Converter para ▸** (PDF, Word, Excel...) · Unir como um único PDF · Abrir

**As ações executam direto, sem abrir nenhuma janela**: o resultado é gravado na mesma pasta e nada aparece na tela. Só há mensagem se algo der errado.
* **Unir** → `primeiro_unido.pdf`;
* **Separar** → pasta `nome - separado`;
* **Converter** → arquivo com o mesmo nome e a nova extensão;
* **Imprimir** → vai para a impressora padrão (ou a última usada), com as opções da última impressão, sempre em uma face.

Nenhum arquivo existente é sobrescrito: se o nome já existir, é usado `nome (2)`. Só **Abrir** e **Organizar páginas** abrem o editor, e *Mais opções...* abre a janela de conversão.

Se vários arquivos estiverem selecionados, o Vorticis junta todos numa única operação. Também são criados atalhos em **Enviar para** (*Vorticis - Unir em PDF* e *Vorticis - Organizar páginas*).
> **Windows 11:** por padrão, o Windows esconde as opções de programas em "Mostrar mais opções". O instalador já oferece, marcada, a opção **"Windows 11: mostrar as opções direto no botão direito"**. Ela também pode ser ligada ou desligada em **Ferramentas › Windows 11: mostrar as opções direto no botão direito**.
> Essa opção ativa o menu completo do Windows (o mesmo de "Mostrar mais opções") diretamente, para todos os programas. Vale só para o seu usuário, não precisa de administrador e é desfeita ao desinstalar. Para aplicar, o Explorer é reiniciado uma vez.

### Informações de salvamento
* **Salvar (`Ctrl+S`) nunca abre janela nem mostra mensagem:** um documento que já existe é atualizado no próprio arquivo. O resultado aparece apenas na barra de status.
* Um documento novo ou convertido é gravado direto, sem perguntar: ao lado do arquivo de origem ou, se não houver, em **Documentos**. Nenhum arquivo existente é apagado; se o nome já existir, é usado `nome (2).pdf`. Os próximos salvamentos atualizam esse arquivo.
* O mesmo vale para as funções da barra: unir, separar, extrair páginas, converter, OCR e salvar texto ou tradução gravam direto na pasta do documento e só informam na barra de status. Para escolher outro nome ou pasta, use **Arquivo › Salvar como**.
* A barra de status indica quantas alterações ainda não foram salvas. Ao fechar, o programa pergunta se quer salvar e lista as alterações.
* Os metadados do PDF são atualizados: data de modificação e produtor *Vorticis PDF Editor*.
* **Arquivo › Histórico de salvamentos** guarda todos os salvamentos, uniões e separações. O histórico fica em `%APPDATA%\Vorticis PDF Editor\historico_salvamentos.jsonl`.
* O salvamento é atômico: o arquivo é gravado num temporário e depois substituído, então uma falha não corrompe o original. As fontes são subconjuntadas para gerar arquivos menores.
* Opcionalmente, o PDF pode ser protegido com senha (AES-256) em **Propriedades › Segurança**.

### Linha de comando
```
VorticisPDF.exe arquivo.pdf
VorticisPDF.exe --merge a.pdf b.pdf planilha.xlsx   (sem janela → a_unido.pdf)
VorticisPDF.exe --split=each a.pdf                  (each, half, every2, every5, every10, oddeven)
VorticisPDF.exe --organize a.pdf b.pdf
VorticisPDF.exe --print a.pdf                       (impressora padrão, sem janela)
VorticisPDF.exe --convert=xlsx a.pdf                (docx, xlsx, pptx, png, jpg, tiff, txt, html, md, odt, pdfa, pdf)
VorticisPDF.exe --to-pdf documento.docx
VorticisPDF.exe --convert a.pdf                     (abre a janela de conversão)
VorticisPDF.exe --register-shell | --unregister-shell
```

### OCR: reconhecer texto de documentos digitalizados
**Ferramentas › Reconhecer texto (OCR)** (`Ctrl+Shift+O`). Funciona **sem internet** e sem instalar nada.
* **Tornar o PDF pesquisável:** adiciona o texto reconhecido como camada invisível. A aparência da página não muda, e o texto passa a poder ser pesquisado, selecionado, copiado e convertido para Word ou Excel.
* **Extrair o texto:** abre o texto reconhecido para copiar, salvar (`.txt` ou `.docx`) ou traduzir.
* Português, inglês e espanhol já vêm incluídos. Outros 20 idiomas (francês, alemão, italiano, japonês, chinês, russo, árabe...) podem ser baixados uma única vez pela própria janela.
* Há três níveis de qualidade (200, 300 ou 400 dpi). As páginas que já têm texto digital podem ser ignoradas.
* Ao abrir um PDF sem texto, o programa sugere o OCR.

### Tradução
**Ferramentas › Traduzir documento** (`Ctrl+Shift+L`). Usa um serviço on-line gratuito, sem cadastro, e por isso requer internet.
* **Novo PDF traduzido mantendo o layout:** cada bloco de texto é trocado pela tradução no mesmo lugar, com tamanho ajustado, sem apagar imagens, linhas ou tabelas.
* **Somente o texto:** abre a tradução lado a lado com o original, para copiar ou salvar.
* São 30 idiomas, com detecção automática do idioma de origem. Em documentos digitalizados, faça o OCR antes de traduzir.

### Assinatura digital com certificado (ICP-Brasil)
Use a ferramenta **Assinar** na barra lateral (`G`) e arraste a área onde o carimbo deve aparecer. Para assinar sem carimbo, use **Ferramentas › Assinar digitalmente (invisível)**.
* **Certificado A1:** arquivo `.pfx` ou `.p12`, com senha.
* **Certificado A3:** token USB ou cartão inteligente, com PIN. O driver do fabricante é detectado automaticamente: SafeNet, Watchdata, GD/Valid, Oberthur, Feitian, Bit4id, OpenSC e outros. Também é possível indicar a `.dll` manualmente.
* Segue o padrão **PAdES** (o mesmo usado pelo gov.br e pelo ITI). O carimbo visível mostra nome, CPF ou CNPJ lido do certificado ICP-Brasil, data e motivo. O motivo, o local e o contato podem ser preenchidos.
* **Carimbo do tempo** opcional, por servidor gratuito, para comprovar a data da assinatura.
* O arquivo original não é alterado, porque a assinatura é gravada num novo arquivo `_assinado.pdf`. Salvar alterações sobre um PDF assinado invalida a assinatura, e a barra de status avisa.
* **Ferramentas › Verificar assinaturas digitais** mostra o signatário, o CPF ou CNPJ, a data e a integridade. Também mostra se o documento foi **alterado depois de assinado** e se o certificado é de uma autoridade confiável instalada no Windows.

### Tema escuro e idioma
* **Exibir › Tema:** *Seguir o Windows* (padrão), *Claro* ou *Escuro*. O botão ☾ / ☀ na barra superior alterna entre eles (`Ctrl+Shift+T`).
* Toda a interface está em **português do Brasil**, inclusive os botões e janelas padrão do sistema (Salvar, Cancelar, seletor de arquivos, impressão, cores) e as mensagens de erro técnicas mais comuns.

### Diagnóstico de erros
Se algo der errado, o programa mostra uma mensagem e continua aberto. Os detalhes, inclusive falhas internas, ficam em **Ajuda › Abrir registro de erros** (`vorticis_erros.log`).

## Compilar a partir do código-fonte

Requer Python 3.10 ou superior no Windows:

```bat
build_windows.bat
```

O script baixa os modelos de OCR e gera `dist\VorticisPDF\VorticisPDF.exe`. Se o [Inno Setup](https://jrsoftware.org/isinfo.php) estiver instalado, também gera o instalador em `installer\Output\`.

Para rodar sem compilar:

```bat
pip install -r requirements.txt
python tools/fetch_tessdata.py
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
  dialogs.py           diálogos (unir, separar, converter, histórico, propriedades)
  inline_edit.py       edição de texto direto na página e barra de edição
  excel_export.py      PDF → Excel (OCR completo, tabelas, colunas e números)
  quick_actions.py     ações diretas do botão direito (unir, separar, converter, imprimir)
  printing.py          janela de impressão em português e impressão
  ocr.py               OCR (Tesseract embutido no PyMuPDF)
  translate.py         tradução de textos e de PDFs mantendo o layout
  signature.py         assinatura digital A1/A3 (pyHanko, PAdES) e verificação
  features.py          diálogos de OCR, tradução e assinatura
  theme.py / icons.py  temas claro/escuro e ícones vetoriais
  i18n.py              tradução pt-BR dos componentes padrão do Qt
  shell_integration.py menu de contexto do Explorer (HKCU)
  single_instance.py   agrupa os arquivos selecionados no Explorer
```

## Licença
GNU AGPL-3.0, a mesma licença do PyMuPDF, que é a base do programa. É software livre e gratuito.
