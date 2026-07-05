export default function EmConstrucao({ titulo }: { titulo: string }) {
  return (
    <>
      <h1 className="titulo">{titulo}</h1>
      <p className="sub">Tela em construção — chega nos próximos passos do M8/M9.</p>
      <section className="card placeholder">
        <div className="placeholder-emoji">🚧</div>
        <div>
          Esta tela será montada sobre a mesma fundação da “Visão geral”,
          consumindo o sidecar. O núcleo Python já entrega todos os números.
        </div>
      </section>
    </>
  )
}
