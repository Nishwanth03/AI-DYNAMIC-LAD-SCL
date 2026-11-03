
export default function CodePreview({ result, error, onDownload }) {
  if (error) {
    return (
      <section className="panel">
        <h3>Generation Error</h3>
        <p className="error">{error}</p>
      </section>
    );
  }

  return (
    <section className="panel output-panel">
      <div className="panel-heading">
        <h3>Generated SCL</h3>
        <span className="language-tag">.SCL</span>
      </div>

      {!result && (
        <div className="empty-state">
          <h3>No code generated yet</h3>
          <p>Enter a control requirement and generate a draft.</p>
        </div>
      )}

      {result && (
        <>
          <p className="result-status">
            Status: {result.status}
          </p>

          {result.scl_code && (
            <>
              <pre className="code">
                <code>{result.scl_code}</code>
              </pre>

              <button className="primary" onClick={onDownload}>
                Download SCL
              </button>
            </>
          )}

          {result.assumptions?.length > 0 && (
            <>
              <h4>Assumptions</h4>
              <ul>
                {result.assumptions.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </>
          )}

          {result.warnings?.length > 0 && (
            <>
              <h4>Warnings</h4>
              <ul className="warnings">
                {result.warnings.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </section>
  );
}
