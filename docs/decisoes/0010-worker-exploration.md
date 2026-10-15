# 0010 — Worker do modo exploration

- **Data:** 2026-10-14
- **Status:** aceita

## Contexto

O backend cria jobs (decisão 0009), mas não executa algoritmos. O worker Python os processa no Supabase, que tem só a amostra publicada (decisão 0004) e o limite de 500 MB do plano gratuito.

## Decisões

- **Features publicadas:** as features dependem do ano inteiro (decisão 0005), que só existe no banco local. A publicação grava os valores já calculados para a amostra (`record_features`, migration 007). Assim, o worker usa exatamente as mesmas features do experimento, sem precisar da base completa.
- **Configuração:** os algoritmos usam a configuração principal do experimento publicado (`--config`); o usuário escolhe só os filtros e `p`.
- **Recorte:** as anomalias são relativas ao recorte filtrado, com o escalador ajustado no próprio recorte.
- **Limites:** mínimo de 100 registros (abaixo disso o limiar de 1% sinalizaria 1 registro ou nenhum) e teto de 50.000, com sorteio reproduzível (semente derivada do id do job) quando o recorte passa do teto.
- **Atomicidade:** execuções, escores e conclusão do job são gravados numa única transação.
- **Retenção:** jobs concluídos são apagados após 24 h. Um job com o recorte máximo grava cerca de 150 mil escores (~13 MB); sem retenção, o limite do Supabase seria atingido em poucas dezenas de jobs. Os resultados do modo exploration não entram no artigo (AGENTS.md, seção 10).
- **Recuperação:** jobs presos em `running` por mais de 30 min (worker interrompido) são marcados como falhos.
- **Reconexão:** se a conexão com o banco cair, o worker tenta reconectar a cada 10 s, em vez de terminar. Motivo: a conexão direta do Supabase só tem IPv6, e na rede de desenvolvimento ela oscilou.

## Consequências

- Republicar o experimento atualiza as features. Registros que saíram da amostra perdem as features e deixam de entrar nos recortes.
- O frontend deve deixar claro que as anomalias são relativas ao recorte e informar quando houve sorteio (`result.sampled`).
- Teste de ponta a ponta no Supabase: job com 4.406 registros (empresas, out–dez/2025) processado em 18,9 s, com 196 registros sinalizados a p = 2%.
