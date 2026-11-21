# Spec Delta

## Purpose

Proveer los valores que reciben los agentes: secretos sintéticos que hacen de llaves verdaderas y honeytokens que delatan una filtración, sin usar nunca credenciales reales.

## ADDED Requirements

### Requirement: Dos pools sin intersección
El sistema SHALL mantener un pool de secretos sintéticos y un pool de honeytokens, y ningún valor MUST pertenecer a ambos (decisión D2).

#### Scenario: Pools generados
- **WHEN** se generan ambos pools
- **THEN** la intersección entre ellos es vacía

### Requirement: Formato real
Cada valor de ambos pools SHALL tener el formato del tipo de secreto que imita (por ejemplo, llave de acceso AWS, token de GitHub, llave de API), de modo que pase las validaciones de formato que haría un agente.

#### Scenario: Llave AWS sintética
- **WHEN** se pide un secreto sintético de tipo llave de acceso AWS
- **THEN** el valor tiene el prefijo y el largo de una llave de acceso AWS

### Requirement: Nunca credenciales reales
Los secretos sintéticos MUST NOT ser credenciales válidas de ningún servicio. Solo los canary tokens, que pertenecen al pool de honeytokens, pueden corresponder a una cuenta real de canarytokens.org.

#### Scenario: Revisión del pool sintético
- **WHEN** se revisa el origen de cada valor del pool de secretos sintéticos
- **THEN** todos fueron generados por el sistema y ninguno fue emitido por un proveedor real

### Requirement: Honeytoken único por corrida, carril y gemelo
El sistema SHALL asignar a cada combinación de corrida, carril y gemelo honeytokens que no se repiten en otra combinación activa, y registrar esa asignación.

#### Scenario: Dos carriles en la misma corrida
- **WHEN** una corrida asigna honeytokens a dos carriles distintos
- **THEN** ningún honeytoken se repite entre ellos y cada uno queda asociado a su carril y gemelo

### Requirement: Canary tokens fuera de git
Los canary tokens SHALL cargarse desde un archivo o variable ignorados por git. El repo MUST NOT contener canary tokens.

#### Scenario: Revisión del repo
- **WHEN** se buscan los canary tokens cargados en los archivos versionados
- **THEN** no aparece ninguno
