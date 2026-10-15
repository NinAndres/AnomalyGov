# 0011 — Frontend

- **Data:** 2026-10-15
- **Status:** aceita

## Decisões

- **React 19 + TypeScript + Vite 6**, em `frontend/`. O Vite 6 foi escolhido porque as versões 7 e 8 exigem Node 20.19 ou superior, e o ambiente usa Node 20.18. Todas as versões estão fixadas no `package.json`.
- **React Router** para URLs compartilháveis: `/experimentos/{nome}`, `/exploracao` e `/exploracao/jobs/{id}`.
- **Sem biblioteca de dados ou de componentes:** `fetch` com hooks próprios (`useApi`, polling do job) e CSS simples. As dependências de execução são só `react`, `react-dom` e `react-router-dom`.
- **Formulário gerado pela definição da base** (`GET /api/sources`): campos de intervalo de meses, seleção múltipla com busca (as UGs têm 2.672 opções) e faixa de valores. Os erros de validação da API aparecem ao lado de cada campo.
- **O job é acompanhado por polling** a cada 1,5 s até concluir (seção 4.2 do AGENTS.md).
- **Avisos fixos na interface:** anomalia não é fraude (rodapé); na exploração, as anomalias são relativas ao recorte, os resultados valem por 24 h, e há aviso quando o recorte foi sorteado.
- **LGPD:** o favorecido pessoa física aparece como "Pessoa física (oculto — LGPD)". O backend já não envia o nome; a interface trata o caso explicitamente.
- **Desenvolvimento:** `npm run dev` repassa `/api` para `http://localhost:5183` (ou `VITE_DEV_API_TARGET`). Em produção, a URL da API vem de `VITE_API_URL`.
- **Testes:** Vitest + Testing Library (`cd frontend && npm test`), com a API simulada.

## Restrição do ambiente

O Vite e o Vitest não funcionam quando o caminho do projeto contém `#` (falham com "module not found"; junções e `subst` não resolvem, porque o Vite segue até o caminho real). Na época desta decisão, o projeto ficava em `Estudos C#`, e a verificação (typecheck, 24 testes e build) foi feita numa cópia do `frontend/`.

**Atualização (2026-10-15):** o projeto foi movido para um caminho sem `#` (`Desktop\TCC\AnomalyGov`), e `npm test` passa no próprio repositório (24 testes). A restrição continua valendo: o projeto não deve voltar para um caminho com `#`.
