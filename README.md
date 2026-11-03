# AI PLC Agent — TIA Portal V19 integration package

This package extends the uploaded project. It preserves the Ollama SCL generation endpoint and adds a local Openness worker project plus website actions for SCL import, LAD XML import, tag creation, and offline PLC compilation.

## Important capability boundaries

- **SCL generation:** retained from the uploaded FastAPI/Ollama implementation.
- **SCL import:** worker uses `ExternalSources.CreateFromFile()` and `GenerateBlocksFromSource()`.
- **LAD import:** worker imports an existing SIMATIC ML XML export. The UI does not yet generate arbitrary new LAD networks from natural language. Use a real V19-exported block XML; renaming an unrelated complex export is not a valid conversion.
- **Tag creation:** worker creates a tag table if missing, checks names and existing global tag addresses, and allocates marker-memory `%M` addresses for tags whose address is blank. Review the address strategy for your CPU/project before use. The code currently supports Bool, Byte, Word, DWord, Int, DInt, Real and Time.
- **Compile:** worker invokes the PLC software compile service and prints compiler state/messages.
- **No PLC download:** there is no download command in the worker or backend.

This source package has **not been compiled against the user's local TIA Portal V19 assemblies**. Siemens DLLs are not redistributed. Build locally and resolve any API/compiler differences against the installed V19 public API.

## 1. Requirements

- Windows 10/11
- TIA Portal V19 with Openness enabled
- User account permitted to use TIA Portal Openness
- Visual Studio 2022 / MSBuild
- .NET Framework 4.8 Developer Pack
- Python 3.10+
- Node.js LTS
- Ollama and `qwen2.5-coder:7b`

## 2. Configure and build C# worker

Open `build_tia_worker.bat` and verify this path:

`C:\Program Files\Siemens\Automation\Portal V19\PublicAPI\V19`

Run `build_tia_worker.bat` from a Visual Studio Developer Command Prompt. The project targets x64 and .NET Framework 4.8. Siemens assemblies are referenced from the local installation and are not included in this ZIP.

Expected output:

` tia-bridge\TIAOpennessWorker\bin\Debug\TIAOpennessWorker.exe `

If MSBuild reports a missing namespace/type/member, save the full compiler output. Do not replace Siemens DLLs with another TIA version.

## 3. Configure backend

Set the Windows environment variables in `.env.example` (FastAPI currently reads process environment variables; it does not automatically parse `.env`):

- `TIA_WORKER_EXE`
- `TIA_TARGET_PROJECT`
- `TIA_TARGET_PLC`
- `OLLAMA_URL`
- `OLLAMA_MODEL`

Use a project that is already open in TIA Portal V19. The worker attaches to an open project by project name and then matches the PLC name.

Start backend:

```powershell
cd D:\AI-PLC-AGENT\backend
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Or run `backend\run_backend.bat`.

## 4. Start frontend

```powershell
cd D:\AI-PLC-AGENT\frontend\ui
npm install
npm run dev
```

Or run `run_frontend.bat` from project root. Open `http://localhost:5173`.

## 5. Website actions

1. Generate SCL, review/edit, then choose **Import SCL into TIA**.
2. To import LAD, place a genuine TIA V19 exported `.xml` block in `generated`, refresh the file list, choose the XML and import.
3. For tag creation, enter JSON such as:

```json
[
  {"name":"Start_PB","data_type":"Bool","address":""},
  {"name":"Motor_Run","data_type":"Bool","address":""},
  {"name":"Speed_Setpoint","data_type":"Real","address":""}
]
```

Empty addresses are automatically assigned in marker memory by the worker after scanning existing global tag tables. The worker creates tags in `AI_Generated_Tags` by default. Verify that `%M` addresses are suitable and not reserved by your project before using them.

4. Select **Compile PLC offline**. All devices must be offline for Openness compilation. Inspect compiler messages in the worker output and TIA Portal.
5. No operation downloads to the PLC.

## 6. API routes

- `GET /health`
- `POST /api/generate`
- `POST /api/import` — SCL
- `POST /api/lad/import` — existing LAD XML
- `GET /api/tia/config`
- `POST /api/tia/test`
- `POST /api/tags/create`
- `POST /api/tia/compile`
- `GET /api/generated`

## 7. Validation and safety

- This application generates drafts; it is not a safety engineering tool.
- Review I/O, interlocks, fail-safe behavior, reset behavior, data types, address allocation, and cross-references.
- Import does not mean logic is correct.
- Compile is not simulation or commissioning.
- Never connect generated logic to a live process without your normal engineering review, test and approval process.
- No PLC download or online write is implemented.


## Dynamic project selection and correct generated-file location

The backend now resolves the project root from `backend/main.py`. Generated SCL/XML files are stored in this installation's `generated` folder, and the default C# worker path is this installation's `tia-bridge/TIAOpennessWorker/bin/Debug/TIAOpennessWorker.exe`. This avoids writing files to a second hardcoded directory.

Open TIA Portal V19 first and open the target project(s). In the web UI click **Refresh projects**, then manually select the project and PLC. No project is selected automatically. The selected full project path and PLC name are included in SCL/LAD import, tag creation and compile requests.

Build the C# worker with `build_tia_worker.bat` on the Windows PC that has TIA Portal V19 and Visual Studio Build Tools installed. The Siemens PublicAPI directory in that batch file must match your installation. Then run `backend\run_backend.bat` and `run_frontend.bat`.

**Feature validation boundary:** Python syntax and frontend source are packaged, but this environment cannot compile against your local Siemens V19 assemblies or attach to your running TIA Portal. You must run the worker build and test discovery/import on your Windows machine. In this source baseline, the C# worker implements DISCOVER/SCL/LAD/EXPORT; the backend tag-create and compile endpoints are present but the uploaded worker source still needs TAGS and COMPILE handlers before those two operations can succeed. LAD generation currently uses the exported V19 reference rung template (two parallel NO contacts), not unrestricted AI-generated arbitrary ladder networks.

No PLC download command is included. Review generated logic, addresses and interlocks and compile offline in TIA before any operational use.
