#!/bin/bash
set -e

# ==============================================================================
# Configuration: Baseline
# ==============================================================================
MACHINE="chrysalis"
#COMPILERS=("intel" "gnu")
COMPILERS=("gnu" "intel")
WORK_HOME="/lcrc/globalscratch/ac.kimy/polaris"
POLARIS_REPO="${WORK_HOME}/repo_baseline"
OMEGA_HOME="${POLARIS_REPO}/polaris/e3sm_submodules/Omega"
POLARIS_SCRATCH_BASE="${WORK_HOME}/polaris_testing"

# Optional/Commented Configuration
MINIFORGE3_HOME="${WORK_HOME}/miniforge3"
# MINIFORGE3_HOME="/lcrc/group/e3sm/ac.kimy/omega/miniforge3"

# ==============================================================================
# Functions
# ==============================================================================

setup_polaris_repo() {
    echo "================================================================================"
    echo "STEP 1: Setting up Polaris Repo (Baseline)"
    echo "================================================================================"
    mkdir -p "${POLARIS_REPO}"
    cd "${POLARIS_REPO}"
    
    # Check if we are inside the 'polaris' folder or need to enter it
    if [ ! -d "polaris" ]; then
        echo "Cloning Polaris repository..."
        git clone git@github.com:E3SM-Project/polaris.git
        cd polaris
    else
        cd polaris
        echo "Repository exists. Resetting to main branch..."
        git fetch origin
        git checkout main
        git reset --hard origin/main
    fi
    
    echo "Updating specific submodules (jigsaw-python, Omega)..."
    git submodule update --init --recursive jigsaw-python
    git submodule update --init --recursive e3sm_submodules/Omega
}

configure_polaris() {
    local compiler=$1
    echo "--------------------------------------------------------------------------------"
    echo "Configuring Polaris for $compiler"
    echo "--------------------------------------------------------------------------------"
    
    if [ ! -f "./configure_polaris_envs.py" ]; then
        echo "Error: configure_polaris_envs.py not found in $(pwd)"
        exit 1
    fi

    ./configure_polaris_envs.py --conda "${MINIFORGE3_HOME}" -c "${compiler}" -m "${MACHINE}"
}

get_parmetis_path() {
    local compiler=$1
    if [ "$compiler" == "intel" ]; then
        echo "/lcrc/soft/climate/polaris/chrysalis/spack/dev_polaris_0_10_0_intel_openmpi/var/spack/environments/dev_polaris_0_10_0_intel_openmpi/.spack-env/view"
    elif [ "$compiler" == "gnu" ]; then
        echo "/lcrc/soft/climate/polaris/chrysalis/spack/dev_polaris_0_10_0_gnu_openmpi/var/spack/environments/dev_polaris_0_10_0_gnu_openmpi/.spack-env/view"
    else
        echo "Error: Compiler $compiler is not supported" >&2
        exit 1
    fi
}

build_omega_dev() {
    local compiler=$1
    local build_dir=$2
    local parmetis_path=$3

    echo "--------------------------------------------------------------------------------"
    echo "Building Omega (dev) with $compiler in $build_dir"
    echo "--------------------------------------------------------------------------------"

    rm -rf "$build_dir"
    mkdir -p "$build_dir"
    pushd "$build_dir" > /dev/null

    cmake \
      -DOMEGA_CIME_MACHINE="${MACHINE}" \
      -DOMEGA_CIME_COMPILER="${compiler}" \
      -DOMEGA_BUILD_TEST=ON \
      -DOMEGA_PARMETIS_ROOT="${parmetis_path}" \
      "${OMEGA_HOME}/components/omega"

    ./omega_build.sh
    popd > /dev/null
}

run_baseline_suite() {
    local compiler=$1
    local dev_build_dir=$2
    
    local scratch_dir="${POLARIS_SCRATCH_BASE}/${compiler}"
    local baseline_dir="${scratch_dir}/baseline_omega_pr"

    echo "--------------------------------------------------------------------------------"
    echo "Running Polaris Baseline Suite for $compiler"
    echo "--------------------------------------------------------------------------------"
    
    local env_file=$(ls load_dev_polaris_*_${MACHINE}_${compiler}_*.sh | head -n 1)
    if [ -f "$env_file" ]; then
        echo "Sourcing $env_file"
        source "./$env_file"
    else
        echo "Warning: Environment file matching 'load_dev_polaris_*_${MACHINE}_${compiler}_*.sh' not found."
    fi

    # Set up baseline suite
    polaris suite -c ocean -t omega_pr --model omega \
        -w "$baseline_dir" \
        -p "$dev_build_dir"

    # Submit baseline job
    if [ -d "$baseline_dir" ]; then
        cd "$baseline_dir"
        echo "Submitting baseline job in $(pwd)..."
        # Fire and forget / continue on error
        sbatch job_script.omega_pr.sh || true
    else
        echo "Error: Baseline directory $baseline_dir was not created."
    fi
    
    cd "${POLARIS_REPO}/polaris"
}

# ==============================================================================
# Main Execution
# ==============================================================================
module load python cmake
setup_polaris_repo

for COMPILER in "${COMPILERS[@]}"; do
    echo "################################################################################"
    echo "Processing Baseline for COMPILER: $COMPILER"
    echo "################################################################################"
    
    configure_polaris "$COMPILER"
    PARMETIS_HOME=$(get_parmetis_path "$COMPILER")
    
    DEVELOP_BUILD="${WORK_HOME}/devbuild_${COMPILER}"

    build_omega_dev "$COMPILER" "$DEVELOP_BUILD" "$PARMETIS_HOME"
    
    run_baseline_suite "$COMPILER" "$DEVELOP_BUILD"
    
    echo "Finished Baseline processing for $COMPILER"
done

echo "Baseline tasks completed successfully."
