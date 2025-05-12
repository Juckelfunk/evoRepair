#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import os


# ------------------- Configuration Values --------------------
depth = 3
tag_id = ""
dir_exp = ""
dir_src = None
dir_build = None
cmd_build = None
cmd_clean = None
cmd_pre_build = None
config_file = None
patch_rank_limit = -1
stack_size = 100
time_out = {
    "solver_unsat": None,  # seconds
    "solver_sat": None,  # seconds
    "total": None,  # minutes
}
use_cache = None
is_debug = False
silence_emitter = False
arg_parsed = False
use_hotswap = False
use_arja = False
mutate_operators = False
mutate_variables = False
mutate_methods = False
init_ratio_perfect = 0
init_ratio_fame = 0
num_perfect_patches = 10
patch_gen_timeout = 1200
test_gen_timeout = 60
num_iterations = 0
dry_run_repair = False
dry_run_test_gen = False
junit_version = "4.11"
passing_tests_partitions = 4
valid_population_size = 40
source_version = None
no_change_localization = False
test_filtered = True
random_seed = None

# ------------------- Directories --------------------
_dir_root = "/".join(os.path.realpath(__file__).split("/")[:-2])
dir_log_base = _dir_root + "/logs"
dir_output_base = _dir_root + "/output"
dir_test = _dir_root + "/tests"
dir_output = ""
dir_log = ""
dir_tmp = _dir_root + "/tmp"
dir_backup = _dir_root + "/backup"
dir_tools = _dir_root + "/tools"
dir_data = _dir_root + "/data"

# ------------------- Files --------------------
file_log_main = ""
file_log_error = dir_log_base + "/log-error"
file_log_last = dir_log_base + "/log-latest"
file_log_build = dir_log_base + "/log-build"
file_log_crash = dir_log_base + "/log-crash"
file_log_cmd = dir_log_base + "/log-command"
file_patch_set = ""
file_junit_jar = "/".join([_dir_root, "extern", "arja", "external", "lib", f"junit-{junit_version}.jar"])
file_oracle_locations = ""
filename_oracle_locations = "oracleLocations.json"

# ------------------- Global Values --------------------
tool_name = "EvoRepair"
iteration_no = 0
count_patch_gen = 0
dir_info = dict()

# ------------------- Time Durations --------------------
time_system_start = 0
time_system_end = 0
total_timeout = 0

# ------------------- LLM Oracle Extraction --------------------
use_llm_extraction = True
file_llm_config = _dir_root + "/llm_config.yml"
file_bug_report = ""
file_extracted_oracle = "" # LLM generated oracle will be saved in this file
llm_generation_override = None # Used when the user specifies an LLM config via --llm-generation
llm_selection_override = None # Used when the user specifies an LLM config via --llm-selection
num_suspicious_locations = 10 # Number of suspicious locations considered when extracting methods for selection

llm_prompt_template = (
        "T wrapper_method(Parameters p ...) {\n"
        "  if (Boolean.parseBoolean(System.getProperty(\"defects4j.instrumentation.enabled\"))) {\n"
        "    T result = original_method(p);\n"
        "    if (<condition_for_buggy_behavior>) {\n"
        "      throw new RuntimeException(\"[Defects4J_BugReport_Violation]\");\n"
        "    }\n"
        "    return result;\n"
        "  } else {\n"
        "    return original_method(p);\n"
        "  }\n"
        "}\n"
    )

# Chart 1
llm_prompt_example_1_bug_report = (
    "Potential NPE in AbstractCategoryItemRender.getLegendItems()\n\n"
    "Setting up a working copy of the current JFreeChart trunk in Eclipse I got a warning about a null pointer access in this bit of code from AbstractCategoryItemRender.java:\n\n"
    "public LegendItemCollection getLegendItems() {\n"
    "LegendItemCollection result = new LegendItemCollection();\n"
    "if (this.plot == null) {\n"
    "return result;\n"
    "}\n"
    "int index = this.plot.getIndexOf(this);\n"
    "CategoryDataset dataset = this.plot.getDataset(index);\n"
    "if (dataset != null) {\n"
    "return result;\n"
    "}\n"
    "int seriesCount = dataset.getRowCount();\n"
    "...\n"
    "}\n\n"
    "The warning is in the last code line where seriesCount is assigned. The variable dataset is guaranteed to be null in this location, I suppose that the check before that should actually read \"if (dataset == null)\", not \"if (dataset != null)\".\n\n"
    "This is trunk as of 2010-02-08.\n"
)

llm_prompt_example_1 = (
    "public LegendItemCollection getLegendItems() {\n"
    "  if (Boolean.parseBoolean(System.getProperty(\"defects4j.instrumentation.enabled\"))) {\n"
    "    try {\n"
    "      return getLegendItems_original();\n"
    "    } catch (NullPointerException e) {\n"
    "        throw new RuntimeException(\"[Defects4J_BugReport_Violation]\");\n"
    "    }\n"
    "  } else {\n"
    "    return getLegendItems_original();\n"
    "  }\n"
    "}"
)

# Time 4
llm_prompt_example_2 = (
    "public Partial with(DateTimeFieldType fieldType, int value) {\n"
    "  if (Boolean.parseBoolean(System.getProperty(\"defects4j.instrumentation.enabled\"))) {\n"
    "    Partial result = with_original(fieldType, value);\n"
    "    try {\n"
    "      new Partial(result.getFieldTypes(), result.getValues());\n"
    "    } catch (IllegalArgumentException e1) {\n"
    "      throw new RuntimeException(\"[Defects4J_BugReport_Violation]\");\n"
    "    }\n"
    "    return result;\n"
    "  } else {\n"
    "    return with_original(fieldType, value);\n"
    "  }\n"
    "}"
)

# Math 53

llm_prompt_example_3_bug_report = (
    "Complex Add and Subtract handle NaN arguments differently, but javadoc contracts are the same\n\n"
    "For both Complex add and subtract, the javadoc states thatn\n\n"
    "     * If either this or <code>rhs</code> has a NaN value in either part,\n"
    "     * {@link #NaN} is returned; otherwise Inifinite and NaN values are\n"
    "     * returned in the parts of the result according to the rules for\n"
    "     * {@link java.lang.Double} arithmeticn\n\n"
    "Subtract includes an isNaN test and returns Complex.NaN if either complex argument isNaN; but add omits this test. The test should be added to the add implementation (actually restored, since this looks like a code merge problem going back to 1.1).\n"
)

llm_prompt_example_3 = (
    "public Complex add(Complex rhs) throws NullArgumentException {\n"
    "    if (Boolean.parseBoolean(System.getProperty(\"defects4j.instrumentation.enabled\"))) {\n"
    "        Complex result = add_original(rhs);\n"
    "        if ((this.isNaN() || rhs.isNaN())\n"
    "                && !(Double.isNaN(result.getReal()) && Double.isNaN(result.getImaginary()))) {\n"
    "            throw new RuntimeException(\"[Defects4J_BugReport_Violation]\");\n"
    "        }\n"
    "        return result;\n"
    "    } else {\n"
    "        return add_original(rhs);\n"
    "    }\n"
    "}"
)
