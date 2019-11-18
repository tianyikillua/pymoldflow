import os
import shutil
import subprocess

import numpy as np

import meshio

from .base import MoldflowAutomation
from .data_io import PatranMesh, convert_to_time_series_xdmf, read_moldflow_xml


class MoldflowResultsExporter(MoldflowAutomation):
    """
    Export Autodesk Moldflow simulation results

    Args:
        moldflow_path (str): Path to Autodesk Moldflow Insight
        sdyfile (str): Autodesk Moldflow ``.sdy`` file containing simulation results
        outdir (str): Output directory
        outfile (str): Output file with a format compatible with `meshio <https://github.com/nschloe/meshio>`_
        use_metric_units (bool): Use Metric units (mm for length for instance)
        verbose (bool): Print out progress information
        stdout (obj): Redirect progress information
    """

    def __init__(
        self,
        moldflow_path,
        sdyfile=None,
        outdir=None,
        outfile=None,
        use_metric_units=True,
        verbose=True,
        stdout=None,
    ):
        super().__init__(moldflow_path, use_metric_units, verbose, stdout)
        self.sdyfile = sdyfile
        self.outdir = outdir
        self.outfile = outfile
        self.mesh = None

    def check(self):
        """
        Check if the provided ``studyrlt.exe`` program works
        """
        self._print("Checking that studyrlt works fine...")
        success, _ = self._run_studyrlt(None)
        return success

    def export_log(self):
        """
        Export analysis log to ``log.txt``

        Returns:
            bool: Success indicator
        """
        log = os.path.join(self._export_dir(), "log.txt")

        # Run studyrlt
        self._print("Exporting log file...")
        success, log_ = self._run_studyrlt("exportoutput")
        if success:
            shutil.move(log_, log)
        return success

    def export_mesh(
        self, output_formats=[], only_export_rawdata=False, return_mesh=False
    ):
        """
        Export and optionally process mesh information

        Args:
            output_formats (list): List of `meshio <https://github.com/nschloe/meshio>`_-compatible mesh formats (MED, XDMF, ...) to be exported
            only_export_rawdata (bool): Whether only export the raw ``.pat`` Patran mesh without processing
            return_mesh (bool): Whether also return the ``meshio`` mesh object

        Returns:
            bool: Success indicator
        """

        mesh = os.path.join(self._rawdata_dir(), "mesh.pat")

        # Run studyrlt if mesh doesn't exist
        if not os.path.isfile(mesh):
            self._print("Mesh: running studyrlt...")
            success, mesh_ = self._run_studyrlt("exportpatran")
            if success:
                shutil.move(mesh_, mesh)
            else:
                return False
        else:
            self._print("Mesh: Patran file already generated")

        if only_export_rawdata:
            return True

        # Read and process mesh
        self._print("Mesh: reading Patran file...")
        self.mesh = PatranMesh(mesh, read_celltypes=["triangle", "tetra"])

        if self.use_metric_units:
            self.mesh.scale()  # convert to mm

        # Only keep one cell type (2d triangular or 3d tetra)
        if "tetra" in self.mesh.cells:
            self.mesh.cell_type = "tetra"
        elif "triangle" in self.mesh.cells:
            self.mesh.cell_type = "triangle"
        self.mesh.cells = {self.mesh.cell_type: self.mesh.cells[self.mesh.cell_type]}
        self.mesh.cellsID = self.mesh.cellsID[self.mesh.cell_type]
        self.mesh.cellsID = dict(
            zip(self.mesh.cellsID, np.arange(len(self.mesh.cellsID)))
        )
        self.mesh.point_data = {}
        self.mesh.cell_data[self.mesh.cell_type] = {}

        # Export to specified formats
        def _output_mesh(ext):
            os.makedirs(self._interfaces_dir(), exist_ok=True)
            out = os.path.join(self._interfaces_dir(), "mesh." + ext)
            meshio.write(out, self.mesh)

        for ext in output_formats:
            _output_mesh(ext)

        if return_mesh:
            return True, self.mesh
        else:
            return True

    def export_result(
        self,
        resultID,
        name,
        only_last_step=True,
        export_npy=False,
        only_export_rawdata=False,
        return_array=False,
    ):
        """
        Export and optionally process simulation results

        Args:
            resultID (int): Identifier of the simulation result (refer to ``results.dat``)
            name (str): Name of the provided simulation result
            only_last_step (bool): Only process the last time-step
            export_npy (bool): Whether also export raw numerical values
            only_export_rawdata (bool): Whether only export the raw ``.xml`` file without processing
            return_array (bool): Whether also return the ``numpy`` array for fields defined at a single time-step

        Returns:
            int: Success indicator, (1) success; (-1) run_studyrlt error; (-2) read_moldflow_xml error
        """
        xml = os.path.join(self._rawdata_dir(), "{}.xml".format(self._io_name(name)))

        # Run studyrlt if xml doesn't exist
        if not os.path.isfile(xml):
            self._print("{}: running studyrlt...".format(name))
            success, xml_ = self._run_studyrlt(resultID)
            if success:
                shutil.move(xml_, xml)
            else:
                if return_array:
                    return -1, None
                else:
                    return -1
        else:
            self._print("{}: XML file already generated".format(name))

        if only_export_rawdata:
            return 1

        self._print("{}: parsing XML...".format(name))
        success, data = read_moldflow_xml(xml, only_last_step=only_last_step)
        if not success:
            if return_array:
                return -2, None
            else:
                return -2

        # Process and export data
        if data["type"] == "NMDT(Non-mesh data)":
            array = self._process_nmdt_result(data, name, return_array=return_array)
        elif data["time"] is None:
            array = self._process_single_result(
                data, name, export_npy=export_npy, return_array=return_array
            )
        else:
            self._process_time_series_result(data, name)

        if return_array:
            return 1, array
        else:
            return 1

    def finalize(self):
        """
        Post-process the output file

        Currently it will generate a time-series XDMF file
        """
        # Convert to a time-series XDMF file
        if os.path.isfile(self.outfile) and ".xdmf" in self.outfile:
            convert_to_time_series_xdmf(self.outfile, backup=False)

    def _export_dir(self):
        if self.outdir is None and self.outfile is not None:
            return os.path.dirname(self.outfile)
        elif self.outdir is None:
            return os.path.dirname(self.sdyfile)
        else:
            return self.outdir

    def _rawdata_dir(self):
        return os.path.join(self._export_dir(), "rawdata")

    def _interfaces_dir(self):
        return os.path.join(self._export_dir(), "interfaces")

    def _io_name(self, name):
        return name.lower().replace(" ", "_").replace("/", "").replace(",", "")

    def _run_studyrlt(self, action):
        sdy = self.sdyfile
        check_mode = False  # flag to verify if studyrlt works fine

        command = [self.studyrlt_exe, self.sdyfile]
        if action == "exportpatran":
            command.append("-exportpatran")
            out_ = sdy.replace(".sdy", ".pat")
        elif action == "exportoutput":
            command.append("-exportoutput")
            out_ = sdy.replace(".sdy", ".txt")
        elif type(action) == int:
            command.append("-xml")
            command.append("{:d}".format(action))
            out_ = sdy.replace(".sdy", ".xml")
        else:
            check_mode = True
        if not check_mode and self.use_metric_units:
            command.append("-unit")
            command.append("Metric")

        if not check_mode:
            assert os.path.isfile(sdy)

        # Execute the command, if there is an execution error, then we
        # have a problem with studyrlt
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
            return False, None

        # If the output does not contain Autodesk, then problem with studyrlt
        output = output.decode("windows-1252").strip()
        if "Autodesk" not in output:
            print("Verify that the given studyrlt.exe works")
            return False, None

        # Directly return for check mode, since no output is expected
        if check_mode:
            return True, None

        # Cleanups
        tmps = [sdy.replace(".sdy", ".out"), sdy.replace(".sdy", ".err")]
        for tmp in tmps:
            if os.path.isfile(tmp):
                os.remove(tmp)

        # If can not find the output file, then we have a problem with studyrlt
        if os.path.isfile(out_):
            os.makedirs(self._rawdata_dir(), exist_ok=True)
            out = os.path.join(self._rawdata_dir(), os.path.basename(out_))
            shutil.move(out_, out)
            return True, out
        else:
            print("Unable to retrieve outputs for {}".format(" ".join(command)))
            return False, None

    def _prepare_data_structure(self, data):
        if data["type"] == "NDDT(Node data)":
            num = len(self.mesh.points)
            locate = self.mesh.pointsID
        else:
            num = len(self.mesh.cells[self.mesh.cell_type])
            locate = self.mesh.cellsID

        if data["dim"] == 1:
            values = np.full(num, np.nan)
        else:
            values = np.full((num, data["dim"]), np.nan)

        return locate, values

    def _process_nmdt_result(self, data, name, return_array=False):
        # TODO: not necessarily time in fact
        # TODO: multidimensional values?

        import xlsxwriter

        x = data["time"]
        y = data["val"]
        assert len(x) == len(y)
        length = len(x)

        if self.outfile is not None:
            # Open an Excel file
            out = os.path.join(self._export_dir(), self._io_name(name) + ".xlsx")
            workbook = xlsxwriter.Workbook(out)
            worksheet = workbook.add_worksheet()
            bold = workbook.add_format({"bold": 1})

            # Dump data
            name = f"{name} ({data['unit']})"
            worksheet.write_row("A1", ["Time (s)", name], bold)
            worksheet.write_column("A2", x)
            worksheet.write_column("B2", y)

            # Plot chart
            chart = workbook.add_chart({"type": "scatter", "subtype": "straight"})
            chart.add_series(
                {
                    "name": ["Sheet1", 0, 1],
                    "categories": ["Sheet1", 1, 0, length, 0],
                    "values": ["Sheet1", 1, 1, length, 1],
                }
            )
            chart.set_x_axis({"name": "Time (s)", "major_gridlines": {"visible": True}})
            chart.set_y_axis({"name": name})
            chart.set_size({"x_scale": 2, "y_scale": 2})
            chart.set_legend({"none": True})
            worksheet.insert_chart("E2", chart)

            workbook.close()

        if return_array:
            return x, y

    def _process_single_result(self, data, name, export_npy=False, return_array=False):

        # Prepare data structure
        locate, values = self._prepare_data_structure(data)

        # Read data
        val = data["val"]
        for identifier, value in val.items():
            try:
                values[locate[identifier]] = value
            except Exception:
                pass

        # For 6-dimensional values, reverse 13 and 23
        if data["dim"] == 6:
            values = values[:, [0, 1, 2, 3, 5, 4]]

        # Export to the output file
        if self.outfile is not None:
            if data["type"] == "NDDT(Node data)":
                self.mesh.point_data[name] = values
            else:
                self.mesh.cell_data[self.mesh.cell_type][name] = values
            meshio.write(self.outfile, self.mesh)

        # Export raw values
        if export_npy:
            os.makedirs(self._interfaces_dir(), exist_ok=True)
            out = os.path.join(self._interfaces_dir(), f"{self._io_name(name)}.npy")
            np.save(out, values)

        # Export array
        if return_array:
            return values
        else:
            return None

    def _process_time_series_result(self, data, name):

        # Prepare PVD information
        timestep = data["time"]
        nsteps = len(timestep)
        name_step = [f"{name}__{t:.4f}" for t in timestep]

        # Read each time-step
        locate, values_ = self._prepare_data_structure(data)
        for i in range(nsteps):

            self._print(f"{name}: reading time-step #{i + 1:d}/{nsteps:d}...")

            # Read data
            values = np.copy(values_)
            for identifier, value in data["val"][i].items():
                try:
                    values[locate[identifier]] = value
                except Exception:
                    pass

            # For 6-dimensional values, reverse 13 and 23
            if data["dim"] == 6:
                values = values[:, [0, 1, 2, 3, 5, 4]]

            # Save to the mesh data structure
            if self.outfile is not None:
                if data["type"] == "NDDT(Node data)":
                    self.mesh.point_data[name_step[i]] = values
                else:
                    self.mesh.cell_data[self.mesh.cell_type][name_step[i]] = values

        # Final write
        if self.outfile is not None:
            meshio.write(self.outfile, self.mesh)
