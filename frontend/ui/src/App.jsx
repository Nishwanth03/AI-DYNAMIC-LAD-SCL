import { useEffect, useState } from "react";
import { checkBackend, generateSCL, importSCL, importLAD, getTiaConfig, testTia, listGenerated, createTags, compilePlc, generateLAD, discoverTiaProjects } from "./services/api";
import "./App.css";

function downloadSCLFile(code, requestedBlockName) {
  const safeBlockName = (requestedBlockName || "PLC_Block")
    .trim()
    .replace(/[^a-zA-Z0-9_-]/g, "_");

  if (!code || !code.trim()) {
    throw new Error("There is no SCL source to download.");
  }

  const blob = new Blob([code], {
    type: "text/plain;charset=utf-8"
  });

  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = `${safeBlockName}.scl`;
  link.style.display = "none";

  document.body.appendChild(link);
  link.click();
  link.remove();

  // Revoke after the browser has started the download.
  window.setTimeout(() => window.URL.revokeObjectURL(url), 1000);
}

export default function App() {
  const [mode,setMode]=useState("SCL");
  const [requirement,setRequirement]=useState("");
  const [blockName,setBlockName]=useState("FB_PumpControl");
  const [blockType,setBlockType]=useState("FB");
  const [ladA,setLadA]=useState("Start_PB"); const [ladB,setLadB]=useState("Auto_Start"); const [ladOut,setLadOut]=useState("Motor_Run");
  const [result,setResult]=useState(null);
  const [files,setFiles]=useState([]);
  const [selectedXml,setSelectedXml]=useState("");
  const [selectedScl,setSelectedScl]=useState("");
  const [tagsText,setTagsText]=useState('[\n  {"name":"Start_PB","data_type":"Bool"},\n  {"name":"Motor_Run","data_type":"Bool"}\n]');
  const [tagPlan,setTagPlan]=useState(null);
  const [tagTable,setTagTable]=useState("AI_Generated_Tags");
  const [config,setConfig]=useState(null);
  const [projects,setProjects]=useState([]);
  const [selectedProject,setSelectedProject]=useState("");
  const [selectedPlc,setSelectedPlc]=useState("");
  const [backend,setBackend]=useState(false);
  const [busy,setBusy]=useState("");
  const [message,setMessage]=useState("");
  const [error,setError]=useState("");
  const [workerLog,setWorkerLog]=useState("");

  async function refresh() {
    try {
      const [h,c,f]=await Promise.all([checkBackend(),getTiaConfig(),listGenerated()]);
      setBackend(true); setConfig(c); setFiles(f.files||[]);
      try { const d=await discoverTiaProjects(); setProjects(d.projects||[]); }
      catch(discoveryError) { setProjects([]); setError(`Backend is online, but TIA discovery is unavailable: ${discoveryError.message}`); }
    } catch(e) { setBackend(false); setError(e.message); }
  }
  useEffect(()=>{refresh();},[]);
  const activeProject = projects.find(p => p.path === selectedProject);
  const selectedTargetReady = Boolean(selectedProject && selectedPlc && activeProject?.plcs?.includes(selectedPlc));
  async function refreshProjects() {
    try { const d = await discoverTiaProjects(); setProjects(d.projects || []); setMessage(`Found ${d.count || 0} open TIA project(s). Select a project and PLC manually.`); }
    catch (e) { setError(e.message); }
  }

  async function generate() {
    setBusy("generate");setError("");setMessage("");setResult(null);
    try {
      if (!blockName.trim()) {
        throw new Error("Please enter a PLC block name before generating.");
      }
      if (mode === "SCL" && !requirement.trim()) {
        throw new Error("Please enter the PLC requirement before generating SCL.");
      }
      if(mode==="SCL") {
        const r=await generateSCL({requirement,block_name:blockName,block_type:blockType});
        setResult(r);
        setSelectedScl(`${r.block_name}.scl`);
        setMessage("SCL draft generated and saved. Refresh the SCL list if it does not appear.");
      } else {
        const r=await generateLAD({block_name:blockName,input_a:ladA,input_b:ladB,output:ladOut});
        setSelectedXml(r.xml_file);setMessage(`LAD template generated: ${r.xml_file}\\nLogic: ${r.logic}\\n${r.limitations}`);
      }
      await refresh();
    } catch(e){setError(e.message);} finally{setBusy("");}
  }
  async function doSclImport() {
    if (!selectedScl) {
      setError("Select an SCL file first.");
      return;
    }
    const selectedSclBase = selectedScl.replace(/\.scl$/i, "");
    if (!selectedTargetReady) {
      setError("Refresh open TIA projects, then select both a project and PLC.");
      return;
    }
    if (!window.confirm(`Import the selected file ${selectedScl} into ${activeProject.name} / ${selectedPlc}? No PLC download will occur.`)) return;
    setBusy("sclimport"); setError(""); setWorkerLog(""); setMessage("");
    try {
      const r = await importSCL({
        block_name: selectedSclBase,
        block_type: result?.block_name === selectedSclBase ? blockType : "FB",
        source_file: selectedScl,
        project_path: selectedProject,
        plc_name: selectedPlc
      });
      setWorkerLog(r.worker_output || "");
      setMessage(`SCL file ${selectedScl} imported to ${activeProject.name} / ${selectedPlc}. Inspect and compile it in TIA Portal. No PLC download was performed.`);
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }

  async function doLadImport() {
    if (!selectedXml) {
      setError("Select a LAD XML file first.");
      return;
    }

    if (!selectedXml.toLowerCase().endsWith(".xml")) {
      setError("LAD import requires a .xml file.");
      return;
    }

    if (!selectedTargetReady) {
      setError("Refresh open TIA projects, then select both a project and PLC.");
      return;
    }

    // Use the selected XML filename as the requested block name rather than
    // the unrelated block name in the generation form.
    const selectedLadBlock = selectedXml.replace(/\.xml$/i, "");

    if (!/^[A-Za-z_][A-Za-z0-9_-]{0,59}$/.test(selectedLadBlock)) {
      setError("The selected XML filename does not produce a valid PLC block name.");
      return;
    }

    const targetLabel = `${activeProject.name} / ${selectedPlc}`;
    if (!window.confirm(
      `Import ${selectedXml} as ${selectedLadBlock} into ${targetLabel}?\n\n` +
      "The XML's internal block name should match its filename. No PLC download will occur."
    )) {
      return;
    }

    setBusy("ladimport");
    setError("");
    setWorkerLog("");
    setMessage("");

    try {
      const r = await importLAD({
        block_name: selectedLadBlock,
        xml_file: selectedXml,
        project_path: selectedProject,
        plc_name: selectedPlc
      });
      setWorkerLog(r.worker_output || "");
      setMessage(
        `LAD XML ${selectedXml} was submitted as ${selectedLadBlock} to ${targetLabel}. ` +
        "Inspect the imported block in TIA Portal. No PLC download was performed."
      );
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }
  async function doTest() {
    setBusy("test");setError("");setMessage("");
    try {const r=await testTia();setMessage(JSON.stringify(r,null,2));}
    catch(e){setError(e.message);} finally{setBusy("");}
  }
  async function doPlan() {
    setError("PLC tag creation is not enabled in this worker build yet. The current C# source does not implement the TAGS command; do not use this action until that handler is added and tested.");
  }
  async function doCompile() {
    setError("Offline compile is not enabled in this worker build yet. The current C# source does not implement the COMPILE command; do not use this action until that handler is added and tested.");
  }
  const scl = result?.scl_code || "";
  return <div className="shell">
    <header><div><div className="brand">AI PLC STUDIO <span>TIA PORTAL V19</span></div><p>Generate · Review · Import · Offline engineering</p></div><div className={backend?"pill good":"pill bad"}>{backend?"Backend online":"Backend offline"}</div></header>
    <main>
      <section className="hero"><div><small>ENGINEERING WORKSPACE</small><h1>AI PLC Agent</h1><p>Generate Siemens SCL drafts and import existing TIA V19 LAD XML using the local Openness worker.</p></div><div className="safety">PLC DOWNLOAD DISABLED</div></section>
      <section className="panel">
        <h2>0. Select open TIA Portal project</h2>
        <p>Project discovery reads projects already open in TIA Portal V19. Nothing is selected automatically.</p>
        <div className="row"><div><label>Open project</label><select value={selectedProject} onChange={e=>{setSelectedProject(e.target.value);setSelectedPlc("");}}><option value="">Select project</option>{projects.map(p=><option key={p.path} value={p.path}>{p.name} — {p.path}</option>)}</select></div><button onClick={refreshProjects} disabled={!!busy}>Refresh projects</button></div>
        <div><label>PLC device</label><select value={selectedPlc} onChange={e=>setSelectedPlc(e.target.value)} disabled={!activeProject}><option value="">Select PLC</option>{(activeProject?.plcs||[]).map(n=><option key={n} value={n}>{n}</option>)}</select></div>
        <p className={selectedTargetReady?"success":"warning"}>{selectedTargetReady?`Selected target: ${activeProject.name} / ${selectedPlc}`:"Project and PLC selection required before import, tag creation or compile."}</p>
      </section>
      <section className="panel">
        <h2>1. Logic generation</h2>
        <div className="tabs"><button className={mode==="SCL"?"active":""} onClick={()=>setMode("SCL")}>SCL</button><button className={mode==="LAD"?"active":""} onClick={()=>setMode("LAD")}>LAD</button></div>
        <label>PLC requirement</label><textarea rows="5" value={requirement} onChange={e=>setRequirement(e.target.value)} placeholder="Describe the required control logic, inputs, outputs, interlocks, fault response and reset conditions."/>
        <div className="row"><div><label>Block name</label><input value={blockName} onChange={e=>setBlockName(e.target.value)}/></div><div><label>Block type</label><select value={blockType} onChange={e=>setBlockType(e.target.value)}><option value="FB">FB</option><option value="FC">FC</option></select></div></div>
        <button className="primary" onClick={generate} disabled={!!busy}>{busy==="generate"?"Generating...":`Generate ${mode}`}</button>
        {mode==="LAD"&&<><div className="row"><div><label>Input A</label><input value={ladA} onChange={e=>setLadA(e.target.value)}/></div><div><label>Input B</label><input value={ladB} onChange={e=>setLadB(e.target.value)}/></div></div><label>Output coil</label><input value={ladOut} onChange={e=>setLadOut(e.target.value)}/><p className="warning">Supported LAD generation pattern: (Input A OR Input B) → Output coil. This uses your exported TIA V19 parallel-branch reference. Other network patterns are not generated automatically yet.</p></>}
      </section>
      {result&&<section className="panel"><h2>2. Review generated SCL</h2><div className="meta">{result.status} · {result.block_name}</div><textarea className="code" rows="20" value={scl} onChange={e=>setResult({...result,scl_code:e.target.value})} spellCheck="false"/><div className="row actions"><button onClick={() => {
        try {
          downloadSCLFile(scl, result?.block_name || blockName);
          setError("");
          setMessage(`Downloaded ${((result?.block_name || blockName).trim().replace(/[^a-zA-Z0-9_-]/g, "_"))}.scl`);
        } catch (e) {
          setError(e.message);
        }
      }}>Download SCL</button><span className="meta">Select the generated file in section 3 to import it.</span></div>{result.status!=="draft"&&<p className="warning">Basic SCL checks found issues. Review and correct the source above. The backend will validate it again before importing.</p>}<ul>{(result.warnings||[]).map((w,i)=><li key={i}>{w}</li>)}</ul></section>}
      <section className="panel">
        <h2>3. Import SCL into TIA Portal</h2>
        <p>Generated SCL source files are listed separately from LAD XML files.</p>
        <div className="row">
          <div>
            <label>Available SCL files</label>
            <select value={selectedScl} onChange={e=>setSelectedScl(e.target.value)}>
              <option value="">Select SCL source</option>
              {files.filter(f=>f.type==="SCL").map(f=><option key={f.name} value={f.name}>{f.name} ({f.size} bytes)</option>)}
            </select>
          </div>
          <button onClick={()=>refresh()} disabled={!!busy}>Refresh files</button>
        </div>
        <p className="warning">The selected SCL file is imported directly from the generated folder. It does not need to be the latest AI draft. Existing PLC blocks with the same name are not overwritten.</p>
        <button className="primary" disabled={!selectedScl || !!busy || !selectedTargetReady} onClick={doSclImport}>
          {busy==="sclimport"?"Importing...":"Import SCL into TIA"}
        </button>
      </section>
      <section className="panel"><h2>4. Import LAD into TIA Portal</h2><p>Choose a previously exported and validated SIMATIC ML XML file in the generated folder.</p><div className="row"><div><label>Available XML files</label><select value={selectedXml} onChange={e=>setSelectedXml(e.target.value)}><option value="">Select LAD XML</option>{files.filter(f=>f.type==="XML").map(f=><option key={f.name} value={f.name}>{f.name}</option>)}</select></div><button onClick={()=>refresh()}>Refresh files</button></div><button className="primary" disabled={!selectedXml||!!busy||!selectedTargetReady} onClick={doLadImport}>{busy==="ladimport"?"Importing...":"Import LAD into TIA"}</button></section>
      <section className="panel"><h2>5. PLC tag address planning</h2><p>The API request model is prepared, but the supplied C# worker does not yet contain the TAGS command. This control remains disabled to prevent a misleading failed operation.</p><label>Tag table name</label><input value={tagTable} onChange={e=>setTagTable(e.target.value)}/><label>Tag definitions (JSON). Leave address empty for automatic %M allocation.</label><textarea rows="6" value={tagsText} onChange={e=>setTagsText(e.target.value)}/><button onClick={doPlan} disabled>Tag creation pending C# TAGS handler</button>{tagPlan&&<pre>{JSON.stringify(tagPlan,null,2)}</pre>}</section>
      <section className="panel"><h2>6. TIA Portal connection</h2><div className="config"><div><small>Worker</small><strong>{config?.worker_exe||"Not configured"}</strong><em>{config?.worker_exists?"Executable found":"Build worker first"}</em></div><div><small>Generated folder</small><strong>{config?.generated_directory||"Not available"}</strong></div><div><small>Selected target</small><strong>{selectedTargetReady?`${activeProject.name} / ${selectedPlc}`:"No target selected"}</strong></div></div><div className="row actions"><button onClick={doTest} disabled={!!busy}>{busy==="test"?"Checking...":"Test configuration"}</button><button className="primary" onClick={doCompile} disabled>Offline compile pending C# COMPILE handler</button></div><p className="warning">A successful path check does not prove Openness attachment. Discovery/import must be verified on the Windows PC with TIA Portal V19.</p></section>
      {message&&<section className="notice"><strong>Result</strong><pre>{message}</pre></section>}
      {workerLog&&<section className="panel"><h2>TIA worker output</h2><pre>{workerLog}</pre></section>}
      {error&&<section className="error"><strong>Operation failed</strong><pre>{error}</pre></section>}
      <footer>AI PLC Agent · Offline engineering only · No PLC download or deployment command</footer>
    </main>
  </div>;
}
