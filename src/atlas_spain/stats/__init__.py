"""Statistical Intelligence: motor estadístico de ATLAS SPAIN.

Solo depende de numpy y scipy (así corre igual en local y en la función serverless).
Las implementaciones de referencia (statsmodels, scikit-learn, PySAL) se usan en los tests
para validar los resultados.

Convenciones:
- Las funciones reciben arrays y descartan NaN de forma explícita: siempre devuelven `n` y
  `n_faltantes` para que el usuario sepa cuántas observaciones entraron en el cálculo.
- Nunca se lanza una excepción por datos insuficientes: se devuelve `None` en el estadístico y
  un aviso en `avisos`.
"""

VERSION = "1.0.0"
