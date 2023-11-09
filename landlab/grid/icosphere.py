import numpy as np

from ..graph import DualIcosphereGraph
from .base import ModelGrid


class IcosphereGlobalGrid(DualIcosphereGraph, ModelGrid):
    """
    Icosphere-based quasi-spherical ("global") Landlab grid.

    Parameters
    ----------
    radius : float, optional
        Radius of the icosphere (default 1)
    mesh_densification_level : int, optional
        Number of times to densify the initial icosahedron (default 0)

    Examples
    --------
    >>> ico = IcosphereGlobalGrid()
    """
    def __init__(self, radius=1.0, mesh_densification_level=0):
        """Initialize the IcosphereGlobalGrid"""
        DualIcosphereGraph.__init__(self, radius, mesh_densification_level)
        ModelGrid.__init__(self)

    def to_vtk(
        self,
        base_name="icosphere",
        field_for_cells=None,
        field_name_for_cells="cell_data",
        field_for_patches=None,
        field_name_for_patches="patch_data",
    ):
        """
        Write grid data to two legacy-VTK-format text files: one for
        nodes and patches, and one for corners and cells.

        Parameters
        ----------
        base_name : str, optional
            Base name for output files (default "icosahedron")
        field_for_cells : ndarray, optional
            Array containing data for each Landlab cell; default None
        field_name_for_cells : str, optional
            Name for field of cell-based values (default "cell_data")
        field_for_patches : ndarray, optional
            Array containing data for each Landlab patch; default None
        field_name_for_patches : str, optional
            Name for field of patch-based values (default "patch_data")

        Examples
        --------
        >>> import os
        >>> ico = IcosphereGlobalGrid()
        >>> ico.to_vtk(field_for_patches=np.zeros(20))
        >>> with open("icosphere_cells.vtk", "r") as f:
        ...     lines = f.readlines()
        >>> lines[4][:15] == "POINTS 20 float"
        True
        >>> with open("icosphere_patches.vtk", "r") as f:
        ...     lines = f.readlines()
        >>> lines[4][:15] == "POINTS 12 float"
        True
        >>> lines[61][:12] == "CELL_DATA 20"
        True
        >>> os.remove("icosphere_cells.vtk")
        >>> os.remove("icosphere_patches.vtk")
        """
        self._points_and_cells_to_vtk(
            self.coords_of_corner,
            self.corners_at_cell,
            base_name + "_cells.vtk",
            field_for_cells,
            field_name_for_cells,
        )
        self._points_and_cells_to_vtk(
            self.coords_of_node,
            self.nodes_at_patch,
            base_name + "_patches.vtk",
            field_for_patches,
            field_name_for_patches,
        )

    @staticmethod
    def _points_and_cells_to_vtk(
        points,
        cells,
        filename="icosphere.vtk",
        scalar_field=None,
        scalar_field_name="cell_data",
    ):
        """
        Save 3D geometry in a vtk-format text file.

        Notes: "cells" is used here in the sense of VTK, as a polygon
        defined by given points; depending on what data are sent in
        the "points" and "cells" parameters, these could be Landlab
        grid nodes and patches, or they could be Landlab grid corners
        and cells.

        Parameters
        ----------
        filename : str, optional
            Name for output file (defaults to "icosahedron.vtk")
        """
        with open(filename, "w") as f:
            f.write("# vtk DataFile Version 2.0\n")
            f.write("Landlab Icosphere Grid\n")
            f.write("ASCII\n")
            f.write("DATASET UNSTRUCTURED_GRID\n")

            # Points: the x, y, z coordinates of each point (node or corner)
            f.write("POINTS " + str(len(points)) + " float\n")
            for p in points:
                f.write(str(p[0]) + " " + str(p[1]) + " " + str(p[2]) + "\n")
            f.write("\n")

            # Cells: here meaning generic 3d polygons on the sphere;
            # either "patches" or "cells" in Landlab terminology
            ncells = len(cells)
            num_points_in_cell = np.count_nonzero(cells + 1, axis=1)
            f.write(
                "CELLS "
                + str(ncells)
                + " "
                + str(np.sum(num_points_in_cell + 1))
                + "\n"
            )
            for i in range(ncells):
                f.write(str(num_points_in_cell[i]))
                for point_id in cells[i]:
                    if point_id > -1:
                        f.write(" " + str(point_id))
                f.write("\n")
            f.write("\n")

            # Cell types: triangle (5) or polygon (7)
            if np.amax(num_points_in_cell) == 3:
                cell_type_line = str(5) + "\n"
            else:
                cell_type_line = str(7) + "\n"
            f.write("CELL_TYPES " + str(ncells) + "\n")
            for _ in range(ncells):
                f.write(cell_type_line)

            # Cell/node data
            if scalar_field is not None:
                f.write("CELL_DATA " + str(len(scalar_field)) + "\n")
                f.write("SCALARS " + scalar_field_name + " float 1\n")
                f.write("LOOKUP_TABLE default\n")
                for value in scalar_field:
                    f.write(str(value) + "\n")

            f.close()
