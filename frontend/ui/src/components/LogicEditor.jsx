
export default function LogicEditor({
  requirement,
  setRequirement,
  blockName,
  setBlockName,
  onGenerate,
  loading,
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h3>Control Requirement</h3>
      </div>

      <label htmlFor="requirement">
        Describe your industrial control logic
      </label>

      <textarea
        id="requirement"
        rows={7}
        value={requirement}
        onChange={(event) => setRequirement(event.target.value)}
        placeholder="Example: Start the pump when Start is pressed..."
      />

      <label htmlFor="blockName">PLC block name</label>

      <input
        id="blockName"
        value={blockName}
        onChange={(event) => setBlockName(event.target.value)}
        placeholder="FB_PumpControl"
      />

      <div className="metadata">
        <span>Language: SCL</span>
        <span>Block type: FB</span>
        <span>Target: Siemens PLC</span>
      </div>

      <button
        className="primary"
        onClick={onGenerate}
        disabled={loading || requirement.trim().length < 10}
      >
        {loading ? "Generating..." : "Generate SCL"}
      </button>
    </section>
  );
}
