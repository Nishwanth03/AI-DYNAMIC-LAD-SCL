
using System;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.Xml;
using System.Reflection;

using Siemens.Engineering;
using Siemens.Engineering.HW;
using Siemens.Engineering.HW.Features;
using Siemens.Engineering.SW;
using Siemens.Engineering.SW.Blocks;
using Siemens.Engineering.SW.ExternalSources;

namespace TIAOpennessWorker
{
    internal class Program
    {
        /*
         * AI PLC AGENT - TIA PORTAL V19
         *
         * SCL:
         * TIAOpennessWorker.exe SCL <project> <plc>
         *     <blockName> <generatedDir> <sclPath>
         *
         * LAD:
         * TIAOpennessWorker.exe LAD <project> <plc>
         *     <blockName> <generatedDir> <xmlPath>
         *
         * EXPORT:
         * TIAOpennessWorker.exe EXPORT <project> <plc>
         *     <blockName> <outputDir>
         */

        static int Main(string[] args)
        {
            string tiaApiPath =
              Environment.GetEnvironmentVariable("TIA_OPENNESS_V19");

            if (string.IsNullOrWhiteSpace(tiaApiPath))
            {
                tiaApiPath =
                    @"C:\Program Files\Siemens\Automation\Portal V19\PublicAPI\V19";
            }

            AppDomain.CurrentDomain.AssemblyResolve += (sender, eventArgs) =>
            {
                string dllName =
                    new AssemblyName(eventArgs.Name).Name + ".dll";

                string dllPath = Path.Combine(tiaApiPath, dllName);

                if (File.Exists(dllPath))
                {
                    return Assembly.LoadFrom(dllPath);
                }

                return null;
            };
            if (args.Length == 1 &&
                args[0].Equals("DISCOVER", StringComparison.OrdinalIgnoreCase))
            {
                return DiscoverProjects();
            }

            string mode;
            string projectPath;
            string plcName;
            string blockName;
            string folderPath;
            string inputFilePath = null;

            if (args.Length == 5 &&
                args[0].Equals("EXPORT",
                    StringComparison.OrdinalIgnoreCase))
            {
                mode = "EXPORT";
                projectPath = args[1];
                plcName = args[2];
                blockName = args[3];
                folderPath = args[4];
            }
            else if (args.Length == 6)
            {
                mode = args[0].ToUpperInvariant();

                if (mode != "SCL" && mode != "LAD")
                {
                    PrintUsage();
                    return 10;
                }

                projectPath = args[1];
                plcName = args[2];
                blockName = args[3];
                folderPath = args[4];
                inputFilePath = args[5];
            }
            else
            {
                PrintUsage();
                return 10;
            }

            try
            {
                projectPath = Path.GetFullPath(projectPath);
                folderPath = Path.GetFullPath(folderPath);

                if (inputFilePath != null)
                    inputFilePath = Path.GetFullPath(inputFilePath);

                string requestedProjectPath = Path.GetFullPath(projectPath);

                Console.WriteLine("AI PLC AGENT - TIA PORTAL V19");
                Console.WriteLine("--------------------------------");
                Console.WriteLine("Mode       : " + mode);
                Console.WriteLine("Project    : " + projectPath);
                Console.WriteLine("PLC        : " + plcName);
                Console.WriteLine("Block      : " + blockName);
                Console.WriteLine("Folder     : " + folderPath);

                if (!File.Exists(projectPath))
                {
                    Console.Error.WriteLine(
                        "TIA project file does not exist.");
                    return 15;
                }

                if (!Regex.IsMatch(
                    blockName,
                    @"^[A-Za-z_][A-Za-z0-9_-]{0,59}$"))
                {
                    Console.Error.WriteLine(
                        "Invalid PLC block name.");
                    return 11;
                }

                if (mode == "EXPORT")
                {
                    Directory.CreateDirectory(folderPath);
                }
                else
                {
                    string generatedRoot =
                        folderPath.TrimEnd(
                            Path.DirectorySeparatorChar,
                            Path.AltDirectorySeparatorChar)
                        + Path.DirectorySeparatorChar;

                    if (inputFilePath == null ||
                        !inputFilePath.StartsWith(
                            generatedRoot,
                            StringComparison.OrdinalIgnoreCase))
                    {
                        Console.Error.WriteLine(
                            "Input file must be inside the generated directory.");
                        return 12;
                    }

                    if (!File.Exists(inputFilePath))
                    {
                        Console.Error.WriteLine(
                            "Input file does not exist: " + inputFilePath);
                        return 13;
                    }

                    if (mode == "SCL")
                    {
                        if (!inputFilePath.EndsWith(
                            ".scl",
                            StringComparison.OrdinalIgnoreCase))
                        {
                            Console.Error.WriteLine(
                                "SCL mode requires a .scl file.");
                            return 14;
                        }

                        string sourceText =
                            File.ReadAllText(
                                inputFilePath,
                                Encoding.UTF8);

                        string expectedDeclaration =
                            @"\bFUNCTION_BLOCK\s+""?" +
                            Regex.Escape(blockName) +
                            @"""?(?=\s|\r|\n|$)";

                        if (!Regex.IsMatch(
                                sourceText,
                                expectedDeclaration,
                                RegexOptions.IgnoreCase) ||
                            !Regex.IsMatch(
                                sourceText,
                                @"\bEND_FUNCTION_BLOCK\b",
                                RegexOptions.IgnoreCase) ||
                            !Regex.IsMatch(
                                sourceText,
                                @"\bBEGIN\b",
                                RegexOptions.IgnoreCase))
                        {
                            Console.Error.WriteLine(
                                "SCL declaration or block structure validation failed.");
                            return 14;
                        }
                    }
                    else
                    {
                        if (!inputFilePath.EndsWith(
                            ".xml",
                            StringComparison.OrdinalIgnoreCase))
                        {
                            Console.Error.WriteLine(
                                "LAD mode requires a SIMATIC ML XML file.");
                            return 14;
                        }

                        XmlReaderSettings settings =
                            new XmlReaderSettings
                            {
                                DtdProcessing =
                                    DtdProcessing.Prohibit,
                                XmlResolver = null
                            };

                        using (XmlReader reader =
                            XmlReader.Create(inputFilePath, settings))
                        {
                            while (reader.Read())
                            {
                                // Check XML well-formedness.
                            }
                        }
                    }
                }

                var processes = TiaPortal.GetProcesses();

                Console.WriteLine(
                    "TIA Portal processes found: " +
                    processes.Count);

                if (processes.Count == 0)
                {
                    Console.Error.WriteLine(
                        "Open TIA Portal V19 and the target project first.");
                    return 22;
                }

                foreach (var process in processes)
                {
                    TiaPortal tiaPortal = null;

                    try
                    {
                        tiaPortal = process.Attach();

                        foreach (Project project in tiaPortal.Projects)
                        {
                            Console.WriteLine(
                                "Open project: " + project.Name);

                            string openedProjectPath = Path.GetFullPath(project.Path.FullName);
                            if (!string.Equals(
                                openedProjectPath,
                                requestedProjectPath,
                                StringComparison.OrdinalIgnoreCase))
                            {
                                continue;
                            }

                            Console.WriteLine(
                                "Matched project: " + project.Name);
                            Console.WriteLine(
                                "Matched project path: " + openedProjectPath);

                            foreach (Device device in project.Devices)
                            {
                                foreach (DeviceItem item in device.DeviceItems)
                                {
                                    PlcSoftware plcSoftware =
                                        FindPlcSoftware(item, plcName);

                                    if (plcSoftware == null)
                                        continue;

                                    Console.WriteLine(
                                        "PLC found: " + plcName);

                                    // EXPORT
                                    if (mode == "EXPORT")
                                    {
                                        PlcBlock block =
                                            FindBlockRecursive(
                                                plcSoftware.BlockGroup,
                                                blockName);

                                        if (block == null)
                                        {
                                            Console.Error.WriteLine(
                                                "Block not found: " +
                                                blockName);
                                            return 23;
                                        }

                                        string exportPath =
                                            Path.Combine(
                                                folderPath,
                                                blockName + ".xml");

                                        if (File.Exists(exportPath))
                                        {
                                            Console.Error.WriteLine(
                                                "Export cancelled. File already exists: " +
                                                exportPath);
                                            return 24;
                                        }

                                        Console.WriteLine(
                                            "Exporting block...");

                                        block.Export(
                                            new FileInfo(exportPath),
                                            ExportOptions.WithDefaults);

                                        Console.WriteLine(
                                            "Export successful: " +
                                            exportPath);

                                        return 0;
                                    }

                                    // PREVENT DUPLICATE BLOCKS
                                    PlcBlock existingBlock =
                                        FindBlockRecursive(
                                            plcSoftware.BlockGroup,
                                            blockName);

                                    if (existingBlock != null)
                                    {
                                        Console.Error.WriteLine(
                                            "Import cancelled. Block already exists: " +
                                            blockName);
                                        return 20;
                                    }

                                    // SCL IMPORT
                                    if (mode == "SCL")
                                    {
                                        foreach (
                                            PlcExternalSource existingSource
                                            in plcSoftware
                                            .ExternalSourceGroup
                                            .ExternalSources)
                                        {
                                            if (string.Equals(
                                                existingSource.Name,
                                                blockName,
                                                StringComparison.OrdinalIgnoreCase))
                                            {
                                                Console.Error.WriteLine(
                                                    "External source already exists: " +
                                                    blockName);
                                                return 21;
                                            }
                                        }

                                        Console.WriteLine(
                                            "Importing SCL external source...");

                                        string fullPath =
                                            Path.GetFullPath(inputFilePath);

                                        string sourceName =
                                            Path.GetFileNameWithoutExtension(
                                                inputFilePath);

                                        // FIX: TWO REQUIRED ARGUMENTS
                                        PlcExternalSource newSource =
                                            plcSoftware
                                            .ExternalSourceGroup
                                            .ExternalSources
                                            .CreateFromFile(
                                                sourceName,
                                                fullPath);

                                        Console.WriteLine(
                                            "Generating PLC block from SCL...");

                                        newSource.GenerateBlocksFromSource();

                                        Console.WriteLine(
                                            "SCL block generation completed.");
                                    }

                                    // LAD IMPORT
                                    else if (mode == "LAD")
                                    {
                                        Console.WriteLine(
                                            "Importing LAD SIMATIC ML XML...");

                                        plcSoftware.BlockGroup.Blocks.Import(
                                            new FileInfo(inputFilePath),
                                            ImportOptions.None);

                                        Console.WriteLine(
                                            "LAD XML import operation completed.");
                                    }

                                    Console.WriteLine(
                                        "PLC download was NOT performed.");

                                    return 0;
                                }
                            }

                            Console.Error.WriteLine(
                                "PLC not found: " + plcName);
                            return 22;
                        }
                    }
                    finally
                    {
                        if (tiaPortal != null)
                            tiaPortal.Dispose();
                    }
                }

                Console.Error.WriteLine(
                    "Target project is not open in the attached TIA Portal process.");

                return 22;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine(
                    "TIA OPENNESS ERROR:");

                Console.Error.WriteLine(ex.ToString());

                return 30;
            }
        }

        // Read-only discovery of projects and PLCs in every running TIA Portal instance.
        // Output format: PROJECT<TAB>name<TAB>full path<TAB>comma-separated PLC names
        private static int DiscoverProjects()
        {
            Console.WriteLine("AI PLC AGENT - TIA PROJECT DISCOVERY");
            Console.WriteLine("-----------------------------------");

            var processes = TiaPortal.GetProcesses();
            Console.WriteLine("TIA Portal processes found: " + processes.Count);

            if (processes.Count == 0)
            {
                Console.WriteLine("No running TIA Portal instances found.");
                return 0;
            }

            int discovered = 0;
            foreach (var process in processes)
            {
                TiaPortal tiaPortal = null;
                try
                {
                    tiaPortal = process.Attach();
                    foreach (Project project in tiaPortal.Projects)
                    {
                        var plcNames = new System.Collections.Generic.List<string>();
                        foreach (Device device in project.Devices)
                            foreach (DeviceItem item in device.DeviceItems)
                                CollectPlcNames(item, plcNames);

                        string path = project.Path == null ? "" :
                            Path.GetFullPath(project.Path.FullName);

                        Console.WriteLine("PROJECT\t" + project.Name + "\t" +
                            path + "\t" + string.Join(",", plcNames.ToArray()));
                        discovered++;
                    }
                }
                catch (Exception ex)
                {
                    Console.Error.WriteLine("Discovery instance error: " + ex.Message);
                }
                finally
                {
                    if (tiaPortal != null)
                        tiaPortal.Dispose();
                }
            }

            Console.WriteLine("DISCOVERY_COMPLETE\t" + discovered);
            return 0;
        }

        private static void CollectPlcNames(
            DeviceItem item,
            System.Collections.Generic.List<string> names)
        {
            if (item == null) return;

            IEngineeringServiceProvider provider = item as IEngineeringServiceProvider;
            if (provider != null)
            {
                SoftwareContainer container = provider.GetService<SoftwareContainer>();
                if (container != null && container.Software is PlcSoftware &&
                    !names.Contains(item.Name))
                    names.Add(item.Name);
            }

            foreach (DeviceItem child in item.DeviceItems)
                CollectPlcNames(child, names);
        }

        // Search PLC blocks in root and nested folders.
        static PlcBlock FindBlockRecursive(
            PlcBlockGroup group,
            string blockName)
        {
            if (group == null)
                return null;

            PlcBlock block =
                group.Blocks.Find(blockName);

            if (block != null)
                return block;

            foreach (PlcBlockGroup childGroup in group.Groups)
            {
                PlcBlock found =
                    FindBlockRecursive(
                        childGroup,
                        blockName);

                if (found != null)
                    return found;
            }

            return null;
        }

        // Recursively locate the target PLC software.
        static PlcSoftware FindPlcSoftware(
            DeviceItem item,
            string targetPlc)
        {
            if (string.Equals(
                item.Name,
                targetPlc,
                StringComparison.OrdinalIgnoreCase))
            {
                IEngineeringServiceProvider provider =
                    item as IEngineeringServiceProvider;

                if (provider != null)
                {
                    SoftwareContainer container =
                        provider.GetService<SoftwareContainer>();

                    PlcSoftware software =
                        container == null
                        ? null
                        : container.Software as PlcSoftware;

                    if (software != null)
                        return software;
                }
            }

            foreach (DeviceItem child in item.DeviceItems)
            {
                PlcSoftware found =
                    FindPlcSoftware(child, targetPlc);

                if (found != null)
                    return found;
            }

            return null;
        }

        static void PrintUsage()
        {
            Console.WriteLine("AI PLC AGENT - TIA PORTAL V19");
            Console.WriteLine("--------------------------------");
            Console.WriteLine("DISCOVER: TIAOpennessWorker.exe DISCOVER");

            Console.WriteLine(
                "SCL: TIAOpennessWorker.exe SCL <project> <plc> <blockName> <generatedDir> <sclPath>");

            Console.WriteLine(
                "LAD: TIAOpennessWorker.exe LAD <project> <plc> <blockName> <generatedDir> <xmlPath>");

            Console.WriteLine(
                "EXPORT: TIAOpennessWorker.exe EXPORT <project> <plc> <blockName> <outputDir>");
        }
    }
}
