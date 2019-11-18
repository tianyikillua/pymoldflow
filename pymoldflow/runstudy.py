import os
import subprocess

from .base import MoldflowAutomation


class MoldflowStudyRunner(MoldflowAutomation):
    """
    Run Autodesk Moldflow study files

    Args:
        moldflow_path (str): Path to Autodesk Moldflow Insight
        use_metric_units (bool): Use Metric units (mm for length for instance)
        verbose (bool): Print out progress information
        stdout (obj): Redirect progress information
    """

    def __init__(self, moldflow_path, use_metric_units=True, verbose=True, stdout=None):
        super().__init__(moldflow_path, use_metric_units, verbose, stdout)

    def run(self, sdyfile, check_mode=False):
        """
        Run a Moldflow simulation using ``runstudy``
        """
        command = [self.runstudy_exe]
        if not check_mode:
            assert os.path.isfile(sdyfile)
            sdyname = os.path.splitext(os.path.basename(sdyfile))[0]
            temp_dir = os.path.join(os.path.dirname(sdyfile), f"runsdytmp_{sdyname}")
            command += [sdyfile, "-temp", temp_dir]
            if self.use_metric_units:
                command += ["-units", "Metric"]

        # Execute the command
        CREATE_NO_WINDOW = 0x08000000
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
        )

        if check_mode:
            output, _ = proc.communicate()
            proc.wait()

            # If the output does not contain Moldflow, then problem with runstudy
            output = output.decode("windows-1252").strip()
            if "Moldflow" not in output:
                print("Verify that the given runstudy.exe works")
                return False
            else:
                return True
        else:
            for line in proc.stdout:
                print(line.decode("windows-1252").strip())

        return True
