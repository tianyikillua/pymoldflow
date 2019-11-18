import os
import subprocess
import tempfile

import yaml
from lxml import etree

from .base import MoldflowAutomation


class MoldflowStudyModifier(MoldflowAutomation):
    """
    Modify Autodesk Moldflow study files

    Args:
        moldflow_path (str): Path to Autodesk Moldflow Insight
        sdyfile (str): Autodesk Moldflow ``.sdy`` file
        outfile (str): Modified ``.sdy`` file for output
        use_metric_units (bool): Use Metric units (mm for length for instance)
        verbose (bool): Print out progress information
        stdout (obj): Redirect progress information
    """

    def __init__(
        self,
        moldflow_path,
        sdyfile=None,
        outfile=None,
        use_metric_units=True,
        verbose=True,
        stdout=None,
    ):
        super().__init__(moldflow_path, use_metric_units, verbose, stdout)
        self.sdyfile = sdyfile
        self.outfile = outfile

        self._initialize_modifier()
        self._read_moldflow_data()

    def add_parameter(self, name, value):
        """
        Modify the simulation file by adding a new parameter

        Args:
            name (str): Name of the parameter
            value (int, float, list, ndarray): New value(s) of the parameter
        """
        for tcodeset_name in self.tcodedata:
            if name in self.tcodedata[tcodeset_name]:
                break
        else:
            print("Unable to find {name} in the parameter database")
            return
        self._add_parameer(tcodeset_name, name, value)

    def define_material(self, name):
        """
        Define the injection material
        """
        if name in self.matdata:
            material = etree.SubElement(self.modifier_, "Material")
            material.set("ID", f"{self.matdata[name]:d}")
        else:
            print("Unable to find {name} in the material database")
            return

    def write(self, export_modifier=False, mpifile=None, check_mode=False):
        """
        Write the modified output file

        Args:
            export_modifier (bool): Whether also export the XML modifier file
            mpifile (str): Create or modify the project file
            check_mode (bool): Only to check if ``studymod`` works
        """
        studymod = os.path.join(self.moldflow_path, "bin", "studymod.exe")
        command = [studymod]
        if not export_modifier:
            modifier_file = tempfile.NamedTemporaryFile(suffix=".xml").name
        else:
            modifier_file = self.outfile.replace(".sdy", ".xml")
        self._modifier(xmlfile=modifier_file)
        if not check_mode:
            command += [self.sdyfile, self.outfile, modifier_file]

        assert os.path.isfile(studymod)
        if not check_mode:
            assert os.path.isfile(self.sdyfile)

        # Execute the command, if there is an execution error, then we
        # have a problem with studymod
        try:
            CREATE_NO_WINDOW = 0x08000000
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW,
            )
            output, _ = proc.communicate()
            proc.wait()
        except subprocess.SubprocessError:
            print("Unable to run {}".format(" ".join(command)))
            return False

        # If the output does not contain Autodesk, then problem with studymod
        output = output.decode("windows-1252").strip()
        if "Autodesk" not in output:
            print("Verify that the given studymod.exe works")
            return False

        # Directly return for check mode, since no output is expected
        if check_mode:
            return True

        # Cleanups
        tmps = [
            self.sdyfile.replace(".sdy", ".out"),
            self.sdyfile.replace(".sdy", ".err"),
        ]
        for tmp in tmps:
            if os.path.isfile(tmp):
                os.remove(tmp)

        # If can not find the output file, then we have a problem with studymod
        if os.path.isfile(self.outfile):
            if mpifile is not None:
                self._write_mpi(mpifile)
            return True
        else:
            print("Unable to generate output file with {}".format(" ".join(command)))
            return False

    def _modifier(self, xmlfile=None):
        """
        Generate the modifier content

        Args:
            xmlfile (str): If given, also write to this file

        Returns:
            str: Content of the modifier file
        """
        string = etree.tostring(
            self.modifier_, xml_declaration=True, encoding="utf-8", pretty_print=True
        ).decode("utf-8")
        if xmlfile is not None:
            with open(xmlfile, "w") as f:
                f.write(string)
        return string

    def _write_mpi(self, mpifile):
        # Create a mpifile if mpifile doesn't exist
        mpiname = os.path.splitext(os.path.basename(mpifile))[0]
        sdybase = os.path.basename(self.outfile)
        sdyname = os.path.splitext(sdybase)[0]
        if not os.path.isfile(mpifile):
            with open(mpifile, "w") as f:
                f.write("VERSION 1.0\n")
                f.write(f'BEGIN PROJECT "{mpiname}"\n')
                f.write(f'STUDY "{sdyname}" {sdybase}\n')
                f.write("END PROJECT\n")
                f.write("ORGANIZE 0\n")
                f.write("BEGIN PROPERTIES\n")
                f.write("END PROPERTIES\n")
        else:
            with open(mpifile, "r") as f:
                lines = f.readlines()
            with open(mpifile, "w") as f:
                for line in lines:
                    if line.startswith("END PROJECT"):
                        f.write(f'STUDY "{sdyname}" {sdybase}\n')
                    f.write(line)

    def _add_parameer(self, tcodeset_name, tcode_name, value):
        assert tcodeset_name in self.tcodedata
        assert tcode_name in self.tcodedata[tcodeset_name]
        if self.prop_ is None:
            self.prop_ = etree.SubElement(self.modifier_, "Property")
        tset = etree.SubElement(self.prop_, "TSet")
        tcodeset = etree.SubElement(tset, "ID")
        tcodeset.text = str(self.tcodedata[tcodeset_name]["ID"])
        subid = etree.SubElement(tset, "SubID")
        subid.text = "1"
        tcodeid = self.tcodedata[tcodeset_name][tcode_name]
        self._add_tcode(tset, tcodeid, tcode_name, value)

    def _add_tcode(self, root, tcodeid, name, value):
        tcode = etree.SubElement(root, "TCode")
        id_ = etree.SubElement(tcode, "ID")
        id_.text = str(tcodeid)
        desc_ = etree.SubElement(tcode, "Description")
        desc_.text = name
        try:
            n = len(value)
        except TypeError:
            n = 1
            value = [value]
        for i in range(n):
            value_ = etree.SubElement(tcode, "Value")
            try:
                value_.text = " ".join([str(x) for x in value[i]])
            except TypeError:
                value_.text = str(value[i])

    def _initialize_modifier(self):
        self.modifier_ = etree.Element(
            "StudyMod", title="Autodesk StudyMod", ver="1.00"
        )
        if self.use_metric_units:
            unit = etree.SubElement(self.modifier_, "UnitSystem")
            unit.text = "Metric"

        self.prop_ = None  # properties

    def _read_moldflow_data(self):
        tcodedata_file = os.path.join(
            os.path.dirname(__file__), "..", "data", "tcodedata.txt"
        )
        with open(tcodedata_file, "r") as fh:
            self.tcodedata = yaml.load(fh, Loader=yaml.FullLoader)

        materials_file = os.path.join(
            os.path.dirname(__file__), "..", "data", "materials.txt"
        )
        with open(materials_file, "r") as fh:
            self.matdata = yaml.load(fh, Loader=yaml.FullLoader)
