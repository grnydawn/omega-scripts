import argparse
import platform
import time
import xml.etree.ElementTree as ET
from xml.dom import minidom
import os
import sys
import glob
import re

# Shared Utilities (Reused/Adapted)

def get_system_info():
    info = {}
    info['OSName'] = platform.system()
    info['Hostname'] = platform.node()
    info['OSRelease'] = platform.release()
    info['OSVersion'] = platform.version()
    info['OSPlatform'] = platform.machine()
    info['Is64Bits'] = "1" if sys.maxsize > 2**32 else "0"
    
    try:
        import psutil
        info['NumberOfLogicalCPU'] = str(psutil.cpu_count(logical=True))
        info['NumberOfPhysicalCPU'] = str(psutil.cpu_count(logical=False))
        info['TotalPhysicalMemory'] = str(int(psutil.virtual_memory().total / (1024 * 1024))) # MB
    except ImportError:
        info['NumberOfLogicalCPU'] = "1"
        info['NumberOfPhysicalCPU'] = "1"
        info['TotalPhysicalMemory'] = "1024"

    info['VendorString'] = "Unknown"
    info['VendorID'] = "Unknown"
    info['FamilyID'] = "0"
    info['ModelID'] = "0"
    info['ProcessorCacheSize'] = "0"
    info['ProcessorClockFrequency'] = "0"
    
    return info

def strip_ansi_codes(text):
    # Regex to remove ANSI escape sequences
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

# Build XML Logic

def generate_build_xml(args, sys_info):
    site = ET.Element("Site")
    site.set("BuildName", args.build_name)
    site.set("BuildStamp", args.build_stamp)
    site.set("Name", args.site_name)
    site.set("Generator", "ctest-3.24.2")
    site.set("CompilerName", "")
    site.set("CompilerVersion", "")
    
    for key, value in sys_info.items():
        site.set(key, value)

    build = ET.SubElement(site, "Build")
    
    start_time = int(time.time())
    ET.SubElement(build, "StartDateTime").text = time.ctime(start_time)
    ET.SubElement(build, "StartBuildTime").text = str(start_time)
    ET.SubElement(build, "BuildCommand").text = "polaris_scan"
    
    # Requirement: "Build is always success without error or warning"
    # So we don't add Warning or Error elements here.

    ET.SubElement(build, "EndDateTime").text = time.ctime(start_time) # Mock instant build
    ET.SubElement(build, "EndBuildTime").text = str(start_time)
    ET.SubElement(build, "ElapsedMinutes").text = "0"
    
    # Pretty print
    xmlstr = minidom.parseString(ET.tostring(site)).toprettyxml(indent="\t")
    
    with open("Build.xml", "w") as f:
        f.write(xmlstr)
    print("Generated Build.xml")

# Test XML Logic

def generate_test_xml(args, sys_info):
    site = ET.Element("Site")
    site.set("BuildName", args.build_name)
    site.set("BuildStamp", args.build_stamp)
    site.set("Name", args.site_name)
    site.set("Generator", "ctest-3.24.2")
    site.set("CompilerName", "")
    site.set("CompilerVersion", "")
    
    for key, value in sys_info.items():
        site.set(key, value)

    testing = ET.SubElement(site, "Testing")
    
    start_time = int(time.time())
    formatted_start_time = time.strftime("%b %d %H:%M %Z", time.localtime(start_time))
    ET.SubElement(testing, "StartDateTime").text = formatted_start_time
    ET.SubElement(testing, "StartTestTime").text = str(start_time)
    
    test_list = ET.SubElement(testing, "TestList")
    
    # Find log files
    log_files = glob.glob(os.path.join(args.log_dir, "*.log"))
    log_files.sort() # Ensure deterministic order
    
    tests = []
    
    if not log_files:
        print(f"Warning: No log files found in {args.log_dir}")

    for log_file in log_files:
        filename = os.path.basename(log_file)
        test_name = filename  # Use filename as test name
        
        # Read content
        try:
            with open(log_file, 'r', errors='replace') as f:
                content = f.read()
                content = strip_ansi_codes(content) # Sanitize
        except Exception as e:
            content = f"Error reading file: {e}"
        
        # Determine status
        # "The test result is fail if there exist "ERROR" word in the log file."
        status = "failed" if "ERROR" in content else "passed"
        
        tests.append({
            'name': test_name,
            'status': status,
            'output': content,
            'path': log_file
        })
        
        ET.SubElement(test_list, "Test").text = f"./{args.log_dir}/{test_name}"

    for test_data in tests:
        test_elem = ET.SubElement(testing, "Test", Status=test_data['status'])
        ET.SubElement(test_elem, "Name").text = test_data['name']
        ET.SubElement(test_elem, "Path").text = f"./{args.log_dir}"
        ET.SubElement(test_elem, "FullName").text = f"./{args.log_dir}/{test_data['name']}"
        ET.SubElement(test_elem, "FullCommandLine").text = f"cat {test_data['path']}"
        
        results = ET.SubElement(test_elem, "Results")
        
        # Dummy Execution Time
        named_meas_time = ET.SubElement(results, "NamedMeasurement", type="numeric/double", name="Execution Time")
        ET.SubElement(named_meas_time, "Value").text = "1.0"
        
        # Completion Status
        named_meas_status = ET.SubElement(results, "NamedMeasurement", type="text/string", name="Completion Status")
        ET.SubElement(named_meas_status, "Value").text = "Completed"
        
        # Command Line
        named_meas_cmd = ET.SubElement(results, "NamedMeasurement", type="text/string", name="Command Line")
        ET.SubElement(named_meas_cmd, "Value").text = f"cat {test_data['path']}"
        
        # Measurement (Log Output)
        measurement = ET.SubElement(results, "Measurement")
        ET.SubElement(measurement, "Value").text = test_data['output']

    formatted_end_time = time.strftime("%b %d %H:%M %Z", time.localtime(int(time.time())))
    ET.SubElement(testing, "EndDateTime").text = formatted_end_time
    ET.SubElement(testing, "EndTestTime").text = str(int(time.time()))
    
    # Write Test.xml
    # Using ElementTree.write to avoid minidom issues with large contents if possible, 
    # but for consistency with others we can try minidom or just straight write.
    # Given potentially large logs, direct write is safer/faster, but minidom gives formatting.
    # Let's stick to ET.write for robustness with large strings.
    tree = ET.ElementTree(site)
    tree.write("Test.xml", encoding="UTF-8", xml_declaration=True)
    print("Generated Test.xml")

# Done XML Logic

def generate_done_xml(args):
    root = ET.Element("Done")
    
    ET.SubElement(root, "buildId").text = args.build_id
    ET.SubElement(root, "time").text = str(int(time.time()))

    xmlstr = minidom.parseString(ET.tostring(root)).toprettyxml(indent="\t")
    
    with open("Done.xml", "w") as f:
        f.write(xmlstr)
    print("Generated Done.xml")

def main():
    parser = argparse.ArgumentParser(description="Generate CDash XML files from log directory")
    
    parser.add_argument("--log-dir", required=True, help="Directory containing log files")
    parser.add_argument("--build-stamp", required=True, help="Build stamp")
    parser.add_argument("--site-name", required=True, help="Name of the site")
    parser.add_argument("--build-name", help="Name of the build (defaults to log folder name)")
    parser.add_argument("--build-id", required=True, help="ID of the build")
    
    args = parser.parse_args()
    
    # Default build name if not provided
    if not args.build_name:
        args.build_name = os.path.basename(os.path.normpath(args.log_dir))
        
    sys_info = get_system_info()
    
    generate_build_xml(args, sys_info)
    generate_test_xml(args, sys_info)
    generate_done_xml(args)

if __name__ == "__main__":
    main()
