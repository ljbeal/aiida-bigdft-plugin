""" Tests for calculations."""
from aiida.engine import run
from aiida.orm import StructureData
from aiida.plugins import CalculationFactory


def test_process(bigdft_code):
    """Test running a calculation
    note this does not test that the expected outputs are created of output parsing"""

    # set up calculation
    cell = [[2, 0, 0], [0, 2, 0], [0, 0, 2]]
    s = StructureData(cell=cell)
    s.append_atom(position=(0, 0, 0), symbols="C")

    inputs = {
        "code": bigdft_code,
        "structure": s,
        "metadata": {
            "options": {
                "jobname": "Mono_Carbon",
                "max_wallclock_seconds": 60,
                "resources": {
                    "num_machines": 1,
                },
                "withmpi": False,
            }
        },
    }

    result = run(CalculationFactory("bigdft"), **inputs)

    assert int(result["energy"].value) == -5
