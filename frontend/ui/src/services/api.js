const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, { headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
  const type = response.headers.get("content-type") || "";
  const data = type.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) { const detail=data?.detail; throw new Error(typeof detail === "string" ? detail : detail ? JSON.stringify(detail,null,2) : `HTTP ${response.status}`); }
  return data;
}
export const checkBackend=()=>request("/health");
export const generateSCL=(payload)=>request("/api/generate",{method:"POST",body:JSON.stringify(payload)});
export const importSCL=(payload)=>request("/api/import",{method:"POST",body:JSON.stringify(payload)});
export const importLAD=(payload)=>request("/api/lad/import",{method:"POST",body:JSON.stringify(payload)});
export const getTiaConfig=()=>request("/api/tia/config");
export const testTia=()=>request("/api/tia/test",{method:"POST",body:"{}"});
export const listGenerated=()=>request("/api/generated");
export const discoverTiaProjects=()=>request("/api/tia/projects");
export const createTags=(table_name,tags,project_path,plc_name)=>request("/api/tags/create",{method:"POST",body:JSON.stringify({table_name,tags,project_path,plc_name})});
export const compilePlc=(project_path,plc_name)=>request("/api/tia/compile",{method:"POST",body:JSON.stringify({project_path,plc_name})});
export const generateLAD=(payload)=>request("/api/lad/generate",{method:"POST",body:JSON.stringify(payload)});
