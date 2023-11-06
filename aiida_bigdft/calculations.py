"""
Calculations provided by aiida_bigdft.

Register calculations via the "aiida.calculations" entry point in setup.json.
"""
import os

import aiida.orm
import yaml
from aiida.common import datastructures
from aiida.engine import CalcJob
from aiida.orm import List, to_aiida_type, SinglefileData

from aiida_bigdft.data.BigDFTParameters import BigDFTParameters
from aiida_bigdft.data.BigDFTFile import BigDFTFile, BigDFTLogfile


class BigDFTCalculation(CalcJob):
    """
    AiiDA calculation plugin wrapping the diff executable.

    Simple AiiDA plugin wrapper for 'diffing' two files.
    """

    _posinp = "posinp.xyz"
    _inpfile = "input.yaml"
    _logfile = "log.yaml"
    _timefile = "time.yaml"

    @classmethod
    def define(cls, spec):
        """Define inputs and outputs of the calculation."""
        super().define(spec)

        # set default values for AiiDA options
        spec.inputs["metadata"]["options"]["resources"].default = {
            "num_machines": 1,
            "num_mpiprocs_per_machine": 1,
            "tot_num_mpiprocs": 1
        }
        spec.inputs["metadata"]["options"]["parser_name"].default = "bigdft"

        # inputs
        spec.input("structure", valid_type=aiida.orm.StructureData, help="Input structure (AiiDA format)")
        spec.input("parameters", valid_type=BigDFTParameters, default=lambda: BigDFTParameters(), help="BigDFT Inputfile parameters, as Dict")

        spec.input("structure_fname", valid_type=aiida.orm.Str, default = lambda: aiida.orm.Str("structure.json"), help="Name override for structure file")
        spec.input("params_fname", valid_type=aiida.orm.Str, default = lambda: aiida.orm.Str("input.yaml"), help="Name override for parameters file")

        spec.input("metadata.options.jobname", valid_type=str, help="Scheduler jobname")

        spec.input("extra_files_send", valid_type=List, serializer = to_aiida_type, default = lambda: List(), help="Extra files to send with calculation")
        spec.input("extra_files_recv", valid_type=List, serializer = to_aiida_type, default = lambda: List(), help="Extra files to retrieve from calculation")

        # outputs
        spec.output("logfile", valid_type=BigDFTLogfile, help="BigDFT calculation Logfile")
        spec.output("timefile", valid_type=BigDFTFile, help="BigDFT calculation time log")
        spec.output("energy", valid_type=aiida.orm.Float, help="Final energy estimate taken from logfile")
        spec.output("ttotal", valid_type=aiida.orm.Float, help="Estimated total run time (excluding queue)")

        spec.exit_code(100, 'ERROR_MISSING_OUTPUT_FILES',
                       message='Calculation did not produce all expected output files.')
        spec.exit_code(101, 'ERROR_PARSING_FAILED',
                       message='Calculation did not produce all expected output files.')
        spec.exit_code(400, 'ERROR_OUT_OF_WALLTIME',
                       message='Calculation did not finish because of a walltime issue.')
        spec.exit_code(401, 'ERROR_OUT_OF_MEMORY',
                       message='Calculation did not finish because of memory limit')

    def prepare_for_submission(self, folder):
        """
        Create input files.

        :param folder: an `aiida.common.folders.Folder` where the plugin should temporarily place all files
            needed by the calculation.
        :return: `aiida.common.datastructures.CalcInfo` instance
        """
        struct_fname = self.inputs.structure_fname.value
        with folder.open(struct_fname, 'w') as o:
            self.inputs.structure.get_ase().write(o)

        # dump params
        params_fname = str(self.inputs.params_fname.value)
        with folder.open(params_fname, 'w') as o:
            yaml.dump(self.inputs.parameters.get_dict(), o)

        # submission parameters
        jobname = self.metadata.options.jobname
        sub_params_file = self.dump_submission_parameters(folder)

        # aiida calcinfo setup
        codeinfo = datastructures.CodeInfo()

        codeinfo.code_uuid = self.inputs.code.uuid
        codeinfo.cmdline_params = ['--structure', self.inputs.structure_fname.value,
                                   '--parameters', self.inputs.params_fname.value,
                                   '--submission', sub_params_file]

        # Prepare a `CalcInfo` to be returned to the engine
        calcinfo = datastructures.CalcInfo()
        calcinfo.codes_info = [codeinfo]

        list_send = []
        for file in self.inputs.extra_files_send.get_list():
            tmp = SinglefileData(os.path.join(os.path.abspath(file)))
            list_send.append( (tmp.uuid, tmp.filename, tmp.filename) )
            tmp.store()

        calcinfo.local_copy_list = list_send

        list_recv = [
            (f'log-{jobname}.yaml', '.', 0),
            (f"./data-{jobname}/time-{jobname}.yaml", ".", 0),
            ("./debug/bigdft-err*", ".", 2),
        ]

        for file in self.inputs.extra_files_recv.get_list():
            list_recv.append( (file, ".", 0) )

        calcinfo.retrieve_list = list_recv

        return calcinfo

    def dump_submission_parameters(self, folder):
        sub_params_file = 'submission_parameters.yaml'
        sub_params = {"jobname": self.metadata.options.jobname}

        sub_params["OMP"] = self.metadata.options.resources.get("num_cores_per_mpiproc", None)
        sub_params["mpi"] = self.metadata.options.resources.get("tot_num_mpiprocs", None)
        sub_params["nodes"] = self.metadata.options.resources.get("num_machines", None)

        sub_params["aiida_resources"] = self.metadata.options.resources

        computer = self.node.computer
        user = aiida.orm.User.objects.get_default()

        sub_params["mpirun command"] = ' '.join(computer.get_mpirun_command())
        sub_params["connection"] = computer.get_authinfo(user).get_auth_params()

        # This actually updates the computer mpirun command permanently
        # self.node.computer.set_mpirun_command([])

        with folder.open(sub_params_file, 'w') as o:
            yaml.dump(sub_params, o)

        return sub_params_file
