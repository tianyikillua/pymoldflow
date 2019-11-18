import os


class MoldflowAutomation:
    """
    Base class for Autodesk Moldflow automation

    Args:
        moldflow_path (str): Path to Autodesk Moldflow Insight
    """

    def __init__(self, moldflow_path, use_metric_units=True, verbose=True, stdout=None):
        self.moldflow_path = moldflow_path
        self.use_metric_units = use_metric_units
        self.verbose = verbose
        self.stdout = stdout

        self.studymod_exe = os.path.join(self.moldflow_path, "bin", "studymod.exe")
        self.runstudy_exe = os.path.join(self.moldflow_path, "bin", "runstudy.exe")
        self.studyrlt_exe = os.path.join(self.moldflow_path, "bin", "studyrlt.exe")
        assert os.path.isfile(self.studymod_exe)
        assert os.path.isfile(self.runstudy_exe)
        assert os.path.isfile(self.studyrlt_exe)

    def _print(self, blabla):
        if self.verbose:
            print(blabla, file=self.stdout)
