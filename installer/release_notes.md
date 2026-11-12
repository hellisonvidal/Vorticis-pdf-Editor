## Downloads

| Arquivo | Para quem |
|---|---|
| **VorticisPDF-Instalador-x.y.z.exe** | Instala no computador (menu Iniciar, atalho, menu do botão direito). **Não pede senha de administrador.** |
| **VorticisPDF-Portatil-x.y.z.zip** | Sem instalação: descompacte e execute `VorticisPDF.exe` (funciona até de um pendrive; não grava nada no computador). |

Requisitos: Windows 10 ou 11 (64 bits).

> **Aviso do Windows SmartScreen** ("O Windows protegeu o computador"): aparece em todo programa novo
> que ainda não tem assinatura digital paga. Clique em **Mais informações → Executar assim mesmo**.
> O código é aberto e os arquivos podem ser conferidos pelo `SHA256SUMS.txt`.

## Novidades da 1.6.0
- **Botão direito executa direto, sem abrir janelas.** Unir, separar, converter e imprimir gravam o resultado na mesma pasta, sem nada aparecer na tela: `_unido.pdf`, pasta `- separado` e o mesmo nome com a nova extensão. A impressão vai para a impressora padrão. Só aparece mensagem se der erro, e nenhum arquivo existente é sobrescrito.
- **Submenu "Converter para ▸"** com todos os formatos: Word, Excel, PowerPoint, PNG, JPG, TIFF, texto, HTML, Markdown, ODT e PDF otimizado. Arquivos do Office e imagens também têm o submenu, com PDF, Word, Excel etc. Há também o submenu **"Separar PDF ▸"**: uma página por arquivo, ao meio, a cada 2, 5 ou 10 páginas, ímpares e pares.
- **Conversão para Excel refeita:**
  - OCR completo automático onde precisa: páginas digitalizadas, tabelas coladas como imagem e texto ilegível;
  - tabelas remontadas célula por célula, também nas digitalizadas;
  - colunas alinhadas em extratos e relatórios;
  - números brasileiros (R$, %, milhar) viram números, datas viram datas, e CPF, CEP e códigos com zero à esquerda são mantidos.
- Corrigido: ao selecionar vários arquivos no Explorer, os processos que iniciavam ao mesmo tempo podiam agir separadamente (por exemplo, gerar dois arquivos unidos em vez de um).

## Novidades da 1.5.1
- Instalador e versão portátil cerca de 100 MB menores: ficaram de fora arquivos que o programa não usa (modelos de IA de layout do PyMuPDF, vídeo do OpenCV e o OpenGL por software do Qt).

## Novidades da 1.5.0
- **Editar texto direto na página:** sem janela separada. Ao clicar no texto, uma caixa de edição aparece no lugar dele, com a fonte, o tamanho e a cor originais. Uma barra no topo troca a fonte, o tamanho e a cor. `Enter` ou um clique fora aplica e `Esc` cancela. Vale também para adicionar texto e para editar vários textos selecionados de uma vez (`Tab` passa para o próximo).
- **Salvar sem janelas:** salvar nunca pergunta nada nem mostra mensagens. Documentos novos ou convertidos são gravados direto ao lado do original ou em Documentos. Unir, separar, extrair páginas, converter, OCR e salvar texto ou tradução também gravam direto e só informam na barra de status. Nenhum arquivo existente é apagado.
- **Nova janela de impressão, toda em português:** impressora e propriedades do driver; páginas (todas, atual, selecionadas, intervalo, ímpares ou pares, ordem inversa); cópias agrupadas; orientação retrato ou paisagem; papel; escala; 2 a 16 páginas por folha; tons de cinza; qualidade. Continua sempre em uma face só.
- **Ícone na barra de tarefas:** o ícone foi refeito num formato que todas as versões do Windows exibem, e os atalhos do instalador ficam ligados ao programa na barra de tarefas.

## Novidades da 1.4.0
- **Impressão direta:** sem pré-visualização própria. Abre a janela de impressão do Windows, com o botão Preferências/Propriedades.
- **Sempre em uma face:** nunca imprime frente e verso, mesmo que a opção esteja marcada nas propriedades da impressora.
- **Seleção de texto sem ferramenta:** com nenhuma ferramenta ativa, basta arrastar o mouse sobre o texto. Para desligar uma ferramenta, clique nela de novo ou pressione Esc.
- **Ferramenta Seleção por retângulos:** desenhe um ou mais retângulos e **edite vários textos ao mesmo tempo**. Tem localizar e substituir em todos e pode trocar fonte, tamanho e cor de todos, mantendo a fonte original de cada texto por padrão. Tudo vira um único passo de desfazer.
- **Salvar um documento existente** apenas atualiza o arquivo original, sem mensagens.
- Corrigido: um clique logo depois de desenhar algo era tomado por clique duplo.
- Corrigido: depois de editar um texto com fontes como a Arial, os espaços eram lidos como "espaço não separável". Com isso, a busca não encontrava o texto editado e a cópia vinha com espaços especiais.

## Novidades da 1.3.0
- **Windows 11:** as opções do Vorticis aparecem direto no menu do botão direito, sem precisar de "Mostrar mais opções". A opção vem marcada no instalador, pode ser ligada ou desligada pelo programa e é desfeita ao desinstalar.
- **Seleção de texto com o mouse, sem escolher ferramenta:** arraste sobre o texto. Clique duplo seleciona a palavra, clique triplo a linha. O botão direito copia, destaca, sublinha, risca ou traduz a seleção.
- **Novo PDF do zero:** escolha o tamanho (A4, Carta, Ofício...), a orientação, o número de páginas e o fundo (em branco, pautado, quadriculado ou pontilhado).
- **Formas:** retângulo, elipse, linha, seta, seta dupla, triângulo, losango, estrela, visto e xis, além de desenho livre. Têm cores, preenchimento, espessura, opacidade e tracejado, e continuam editáveis: dá para mover, redimensionar e excluir.

## Novidades da 1.2.0
- **OCR completo:** reconhece o texto de documentos digitalizados, sem internet. Pode tornar o PDF pesquisável ou extrair o texto. Português, inglês e espanhol já vêm incluídos, e há mais 20 idiomas para baixar.
- **Tradução:** gera um PDF traduzido mantendo o layout, ou só o texto, em 30 idiomas.
- **Assinatura digital com certificado A1 (.pfx) ou A3 (token/cartão),** no padrão PAdES/ICP-Brasil. Tem carimbo visível com nome e CPF/CNPJ, carimbo do tempo opcional e verificação de assinaturas.
- **Tema escuro** (ou seguir o tema do Windows).
- **Interface 100% em português,** inclusive botões e janelas padrão do sistema.
- **Corrigido** o erro *"argument should be a str or an os.PathLike object ... not 'NoneType'"*, que aparecia ao clicar em "Nenhum arquivo aberto recentemente" na tela inicial.

## Novidades da 1.1.0
- Corrigido o travamento seguido de fechamento ao unir dois ou mais PDFs.
- Visual renovado: ícones vetoriais, barra de ferramentas lateral e tela inicial.
- Salvar e Imprimir com ícones.
- Detecção de fonte mostrada ao passar o mouse e no editor (com prévia na fonte original).
- O texto editado não sobrescreve mais linhas, tabelas, marcações ou textos vizinhos.
- Registro de erros para diagnóstico (Ajuda › Abrir registro de erros).

Desenvolvido integralmente com Inteligência Artificial — gratuito, hoje e sempre.
