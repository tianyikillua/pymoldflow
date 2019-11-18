import os
import shutil
import numpy as np


class PatranMesh:
    """
    Class for Patran mesh compatible with ``meshio``

    Args:
        pat (str): Patran file
        read_celltypes (list): List of cell types to be read: ``line``, ``triangle``, ``quad``, ``tetra`` and ``hexahedron``
    """
    def __init__(self, patfile, read_celltypes=["triangle", "tetra"]):
        self.read(patfile, read_celltypes=read_celltypes)
        self.init_mesh()

    def read(self, patfile, read_celltypes):
        """
        Read points and cells of a Patran mesh
        """
        import re

        def get_points(line):
            line = line.strip()
            points = re.findall(r"[-\d\.]+E...", line)
            points = [float(point) for point in points]
            return points

        def get_cell(line, num_points, pointsID):
            line = line.strip()
            cell = re.findall(r"[\d]+", line)[:num_points]
            cell = [pointsID[int(point)] for point in cell]
            return cell

        meshio_to_patran_type = {
            "line": 2,
            "triangle": 3,
            "quad": 4,
            "tetra": 5,
            "hexahedron": 8,
        }

        patran_to_meshio_type = {}
        assert len(read_celltypes) > 0
        for celltype in read_celltypes:
            patran_to_meshio_type[meshio_to_patran_type[celltype]] = celltype

        # Read patran file
        f = open(patfile, "r")
        lines = f.read()
        lines = lines.replace(" ", ",")
        for _ in range(15):
            lines = lines.replace(",,", ",")

        # Read points
        self.pointsID = {}
        self.points = []
        pointlines = re.findall(r"\n(,1,[\d,]+\n[,\d.EG\+-]+\n1[G,\d]+)", lines)
        for i, n in enumerate(pointlines):
            self.pointsID[int(n.split("\n")[0].split(",")[2])] = i
            self.points.append(get_points(n.split("\n")[1]))
        self.points = np.array(self.points)

        # Read cells
        self.cellsID = {}
        self.cells = {}
        celllines = re.findall(r"\n,2,([\d,E]+\n[\d\.\+,E]+\n[\d,E]+)", lines)
        for e in celllines:
            celltype = int(e.split(",")[1])
            num_points = int(e.split("\n")[1].split(",")[1])
            if celltype not in patran_to_meshio_type:
                continue
            meshio_type = patran_to_meshio_type[celltype]
            cellID = int(e.split(",")[0])
            cell = get_cell(e.split("\n")[2], num_points, self.pointsID)
            if meshio_type in self.cellsID:
                self.cellsID[meshio_type].append(cellID)
                self.cells[meshio_type].append(cell)
            else:
                self.cellsID[meshio_type] = [cellID]
                self.cells[meshio_type] = [cell]

        for key in self.cells:
            self.cells[key] = np.array(self.cells[key], dtype=int)
            self.cellsID[key] = np.array(self.cellsID[key], dtype=int)

        self.point_data = {}
        self.cell_data = {}
        self.field_data = {}

    def init_mesh(self):
        self.ncells_cumsum = np.cumsum([len(cells) for cells in self.cells.values()])
        self.ncells = self.ncells_cumsum[-1]
        self.remove_free_points()
        self.npoints = len(self.points)
        self.ncells_per_point_ = None

    def scale(self, factor=1e3):
        """
        Scale the coordinates by a factor
        """
        self.points *= factor

    def ncells_per_point(self):
        """
        Number of cells that every point is connected to
        """
        if self.ncells_per_point_ is not None:
            return self.ncells_per_point_
        else:
            self.ncells_per_point_ = np.zeros(len(self.points), dtype=int)
            for celltype in self.cells:
                for cell in self.cells[celltype]:
                    self.ncells_per_point_[cell] += 1
            return self.ncells_per_point_

    def remove_free_points(self):
        """
        Remove free points from coordinates and cell connectivities
        """
        # Find which points are not mentioned in the cells
        all_cells_flat = np.concatenate(
            [vals for vals in self.cells.values()]
        ).flatten()
        free_points = np.setdiff1d(np.arange(len(self.points)), all_cells_flat)
        if len(free_points) == 0:
            return

        # Remove free points
        self.points = np.delete(self.points, free_points, axis=0)
        for key in self.point_data:
            self.point_data[key] = np.delete(self.point_data[key], free_points, axis=0)

        # Adjust cell connectivities
        diff = np.zeros(len(all_cells_flat), dtype=int)
        for free_point in free_points:
            diff[np.argwhere(all_cells_flat > free_point)] += 1
        all_cells_flat -= diff
        k = 0
        for key in self.cells:
            s = self.cells[key].shape
            n = np.prod(s)
            self.cells[key] = all_cells_flat[k:k + n].reshape(s)
            k += n

        # Adjust pointsID
        pointsID_keys = np.fromiter(self.pointsID.keys(), int)
        pointsID_keys = np.delete(pointsID_keys, free_points)
        pointsID_values = np.arange(len(pointsID_keys))
        self.pointsID = dict(zip(pointsID_keys, pointsID_values))

    def average_cell_to_point(self, tetra_data):
        """
        Average data defined at tetra cells to nodes
        """
        if tetra_data.ndim == 1:
            point_data = np.zeros(self.npoints)
        else:
            assert tetra_data.ndim == 2
            point_data = np.zeros((self.npoints, tetra_data.shape[1]))

        ncells_per_point = np.zeros(self.npoints, dtype=int)
        for i, cell in enumerate(self.cells["tetra"]):
            ncells_per_point[cell] += 1
            point_data[cell] += tetra_data[i]

        point_data /= ncells_per_point[:, None]
        return point_data

    def average_point_to_cell(self, point_data):
        """
        Average data defined at points to tetra cells
        """
        if point_data.ndim == 1:
            tetra_data = np.zeros(self.ncells)
        else:
            assert point_data.ndim == 2
            tetra_data = np.zeros((self.ncells, point_data.shape[1]))
        for i, cell in enumerate(self.cells["tetra"]):
            tetra_data[i] = np.mean(point_data[cell], axis=0)
        return tetra_data


def read_moldflow_xml(fxml, only_last_step=False):
    """
    Read a Moldflow XML result file

    data["name"]: result name
    data["type"]: NDDT(Node data), ELDT(Element data) or NMDT(Non-mesh data)
    data["unit"]: physical unit
    data["time"]: list of times if exist
    data["val"]: identifiers and corresponding values
    """
    from lxml import etree as ET

    parser = ET.XMLParser(encoding="windows-1252", remove_comments=True, huge_tree=True)
    try:
        tree = ET.parse(fxml, parser)
    except ET.ParseError:
        return False, None
    root = tree.getroot()[1]

    # Basic information
    data = {}
    data["name"] = root.attrib["Name"].strip()
    data["type"] = root.find("DataType").text.strip()
    data["unit"] = root.find("DeptVar").attrib["Unit"]
    data["dim"] = int(root.find("NumberOfComponents").text)

    if data["type"] != "NMDT(Non-mesh data)":
        datasets = root.xpath("Blocks/Block/Data")
        if only_last_step:
            datasets = [datasets[-1]]
    else:
        datasets = root.xpath("Blocks/Block/DeptValues")
    nsteps = len(datasets)

    data["time"] = np.zeros(nsteps)
    if data["type"] != "NMDT(Non-mesh data)":
        if nsteps <= 1 or only_last_step:
            data["time"] = None

    if data["type"] != "NMDT(Non-mesh data)":
        data["val"] = {}
    else:
        if data["dim"] == 1:
            data["val"] = np.zeros(nsteps)
        else:
            data["val"] = np.zeros((nsteps, data["dim"]))

    for i, dataset in enumerate(datasets):

        if data["time"] is not None:
            try:
                data["time"][i] = float(dataset.getprevious().getprevious().attrib["Value"])
            except(AttributeError, KeyError):
                data["time"][i] = np.nan

        # For mesh data, loop
        if data["type"] != "NMDT(Non-mesh data)":
            id_val = {}
            for val in dataset:
                identifier = int(val.attrib["ID"])
                array = np.fromstring(
                    val.find("DeptValues").text, sep=" ", count=data["dim"]
                )
                array[array > 1e29] = np.nan
                if len(array) == 1:
                    id_val[identifier] = array[0]
                else:
                    id_val[identifier] = array

            if data["time"] is not None:
                data["val"][i] = id_val
            else:
                data["val"] = id_val

        # For non-mesh data, just read
        else:
            array = np.fromstring(dataset.text, sep=" ", count=data["dim"])
            if len(array) == 1:
                data["val"][i] = array[0]
            else:
                data["val"][i] = array

    return True, data


def convert_to_time_series_xdmf(fxdmf, backup=False):
    """
    Convert a plain XDMF file to
    a time-series one readable by ParaView
    """
    # Backup if needed
    assert os.path.splitext(fxdmf)[1] == ".xdmf"
    if backup is not False:
        assert type(backup) == str
        shutil.copyfile(fxdmf, backup)

    # Parse XDMF
    from copy import deepcopy
    from lxml import etree as ET

    parser = ET.XMLParser(remove_blank_text=True)
    tree = ET.parse(fxdmf, parser)
    root = tree.getroot()

    # Retrieve mesh information
    geometry = root.xpath("//Geometry")[0]
    topology = root.xpath("//Topology")[0]

    # Read all functions inside HDF5
    # Those that are a function of time is of format [name__time]
    # See self._process_time_series_result
    func_all = root.xpath("//Attribute/@Name")
    func_ele = root.xpath("//Attribute")

    # Unique functions
    func_set = []
    for f in func_all:
        name = f.split("__")[0]
        if name not in func_set:
            func_set.append(name)

    # Concatenate all time steps
    timestep = [f.split("__")[1] for f in func_all if len(f.split("__")) > 1]
    timestep = sorted(list(set(timestep)), key=float)

    # Time steps for a particular function
    def _f_timestep(func):
        f_ts = []
        for f in func_all:
            if f.split("__")[0] == func and len(f.split("__")) > 1:
                f_ts.append(f.split("__")[1])
        return f_ts

    # Given a time-value and a function, return the corresponding XML element
    def _func_at(func, t):
        f_ts = _f_timestep(func)
        # Single time-step functions
        if len(f_ts) == 0:
            ind = func_all.index(func)
            element = deepcopy(func_ele[ind])

        # For functions containing several time-steps
        # Use the maximum time-step that is <= t
        # If the above set is empty, use the smallest available time-step
        else:
            if t in f_ts:
                t = t
            else:
                f_t_ll_t = [f_t for f_t in f_ts if float(f_t) < float(t)]
                if len(f_t_ll_t) > 0:
                    t = max(f_t_ll_t, key=float)
                else:
                    t = f_ts[0]
            ind = func_all.index(func + f"__{t}")
            element = deepcopy(func_ele[ind])
            element.attrib["Name"] = func
        return element

    # Complete grid at a time
    def _time_series_grid(t):
        grid = ET.Element("Grid", Name="Moldflow results", GridType="Uniform")

        # Append current time value
        grid.append(ET.Element("Time", Value=t))

        # Append mesh information
        grid.append(deepcopy(geometry))
        grid.append(deepcopy(topology))

        # Loop on all unique functions
        for func in func_set:
            grid.append(_func_at(func, t))

        return grid

    # Loop on all time steps if time-steps exis
    if len(timestep) > 0:
        domain = root.xpath("//Domain")[0]
        timeseries = ET.Element(
            "Grid", Name="TimeSeries", GridType="Collection", CollectionType="Temporal"
        )
        for t in timestep:
            timeseries.append(_time_series_grid(t))
        domain.append(timeseries)
        domain.remove(domain[0])

    # Output to replace the current file
    tree.write(fxdmf, pretty_print=True)
