/**
 * Utilitário de leitura de arquivo do usuário (Contrato PDF e Importar CSV).
 *
 * O conteúdo vai ao sidecar como base64 do ARQUIVO CRU: a interpretação
 * (texto do PDF, encoding do CSV) é toda do backend — o front não decodifica.
 */

/** Lê o arquivo e devolve o conteúdo em base64 (em blocos, sem estourar a pilha). */
export async function arquivoParaBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer())
  let binario = ''
  const BLOCO = 0x8000
  for (let i = 0; i < bytes.length; i += BLOCO) {
    binario += String.fromCharCode(...bytes.subarray(i, i + BLOCO))
  }
  return btoa(binario)
}
