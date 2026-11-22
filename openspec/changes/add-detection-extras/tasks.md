# Tasks

## 1. Fragmentos entre peticiones

- [x] 1.1 Implementar `scanner.tokens_of`, `fragment_min_len` y `fragment_coverage`; verificar la cobertura y que el prefijo común `AKIA` no alcanza
- [x] 1.2 Implementar la ventana de peticiones y `LeakTracker.scan_fragments`; verificar los escenarios de llave en tres peticiones y de trozos insuficientes

## 2. Canary

- [x] 2.1 Parear el `secret` de la canary con la `AWS_SECRET_ACCESS_KEY` de la caja; verificar que el pool B nunca recibe canaries
- [x] 2.2 Implementar la firma SigV4 y `canary.use_key`; verificar contra el vector `get-vanilla` de AWS
- [x] 2.3 Disparar la canary una vez al llegar al atacante y emitir `canary.trigger`; verificar con un transporte simulado que el secret key no aparece en los eventos
- [ ] 2.4 Generar canaries reales con `secret` en `secrets/canaries.json` y probar el disparo en el deploy

## 3. Divergencia entre gemelos

- [x] 3.1 Registrar las acciones y salidas por caja en los hooks
- [x] 3.2 Implementar `divergence.compare`; verificar los escenarios de valores sustituidos y de fuga contrafactual
- [x] 3.3 Agregar `divergence` al resultado del gemelo y emitir `twin.divergence`

## 4. Cadena del ataque

- [x] 4.1 Implementar `chain.build_chain` y `GET /runs/{id}/chain`; verificar con una corrida de punta a punta

## 5. Ablaciones

- [x] 5.1 Agregar `ablate` a `RunRequest` y `Run`, y aplicarlo en el aprovisionamiento, el traspaso, los hooks del bajo y el veredicto
- [x] 5.2 Verificar `honeytokens`, `diff_scan` y el rechazo sin el carril gemelo
- [x] 5.3 Medirlas en `eval/run_eval.py` con `EVAL_ABLATIONS` y escribir `ablations.json`
- [ ] 5.4 Correr las ablaciones contra la API desplegada y llevar los números al pitch
