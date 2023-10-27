#!/usr/bin/python
"""
icosphere_global_grid: Create a Landlab global (i.e., quasi-spherical)
grid based on an IcoSphere, which is formed by iteratively densifying
an icosahedron.

Greg Tucker, University of Colorado Boulder, September 2023
"""

import numpy as np

from landlab.utils.geometry.spherical import (
    arc_length,
    area_of_sphertri,
    cartesian_to_spherical,
    rotate_zy,
)

from .refinable_icosahedron import RefinableIcosahedron


class DualIcosphereGraph:
    """
    A Landlab global (quasi-spherical) graph type based on an IcoSphere.

    Parameters
    ----------
    radius : float, optional
        Radius for the icosphere, m (default 1)
    mesh_densification_level : int, optional
        Number of iterative subdivisions of initial triangles (default 0)
    """

    def __init__(self, radius=1.0, mesh_densification_level=0):
        """
        Initialize DualIcosphereGraph

        Notes
        -----
        Data structures set up include:
        - coords_of_node : ndarray of float (n_nodes, 3)
        - x_of_node, y_of_node, z_of_node : ((n_nodes, ) views of coords_of_node)
        - coords_of_corner : ndarray of float (n_corners, 3)
        - x_of_corner, y_of_corner, z_of_corner : ndarray of float (n_corners, )
        - length_of_link : ndarray of float (n_links, )
        - nodes_at_link, node_at_link_tail, node_at_link_head
        - links_at_node
        - cell_at_node, node_at_cell
        - corners_at_face
        - corners_at_node, corners_at_cell
        - area_of_cell
        - length_of_face
        - link_at_face, face_at_link
        - faces_at_cell

        Examples
        --------
        >>> import numpy as np
        >>> ico = DualIcosphereGraph()
        >>> np.round(ico.coords_of_node[0], 3)
        array([-0.526,  0.851,  0.   ])
        >>> np.round(ico.coords_of_corner[1], 3)
        array([-0.   ,  0.934,  0.357])
        >>> round(ico.length_of_link[0], 3)
        1.107
        >>> ico.nodes_at_link[0]
        array([ 0, 11])
        >>> ico.links_at_node[0]
        array([ 0,  2,  4,  6,  8, -1])
        >>> ico.cell_at_node[0]
        0
        >>> ico.node_at_cell[1]
        1
        >>> ico.corners_at_face[0]
        array([0, 4])
        >>> int(10000 * ico.length_of_face[0])
        7297
        >>> ico.corners_at_node[0]
        array([ 3,  4,  0,  1,  2, -1])
        >>> int(1e6 * ico.area_of_cell[0])
        1047197
        >>> ico.link_at_face[2]
        2
        >>> ico.face_at_link[3]
        3
        >>> ico.faces_at_cell[0]
        array([ 0,  2,  4,  6,  8, -1])
        """
        ico = RefinableIcosahedron(radius)
        if mesh_densification_level > 0:
            ico.refine_triangles(mesh_densification_level)

        self.radius = radius
        self.setup_nodes(ico.vertices)
        self.setup_links(ico.faces)
        self.setup_patches_and_corners(ico.faces)
        self.setup_faces()
        self.setup_cells()

    def setup_faces(self):
        """
        Create corners_at_face and length_of_face.
        """

        # Set up a temporary dict to look up patches by pairs of shared nodes.
        patches_at_node_pair = {}
        for i in range(self.number_of_patches):
            for j in range(3):
                n1 = self.nodes_at_patch[i, j - 1]
                n2 = self.nodes_at_patch[i, j]
                key = (min(n1, n2), max(n1, n2))
                try:
                    patch1 = patches_at_node_pair[key]
                    patches_at_node_pair[key] = (min(i, patch1), max(i, patch1))
                except KeyError:
                    patches_at_node_pair[key] = i

        self.number_of_faces = self.number_of_links
        self.corners_at_face = np.zeros((self.number_of_faces, 2), dtype=int)
        self.length_of_face = np.zeros(self.number_of_faces)
        for face in range(self.number_of_faces):
            ln1 = min(self.nodes_at_link[face])
            ln2 = max(self.nodes_at_link[face])
            cnr0, cnr1 = patches_at_node_pair[(ln1, ln2)]
            # print(link, ln1, ln2, patches_at_link)
            # the corners are the same as patches, and faces same as links, so we
            # can assign the two corners (patches) to the face (link)
            self.corners_at_face[face, 0] = cnr0
            self.corners_at_face[face, 1] = cnr1
            self.length_of_face[face] = self.radius * arc_length(
                self.coords_of_corner[cnr0], self.coords_of_corner[cnr1], self.radius
            )

    def setup_nodes(self, ico_vertices):
        """
        Set up the arrays coords_of_node, x_of_node, y_of_node, z_of_node
        (the latter 3 being views of the coords_of_node).

        Parameters
        ----------
        ico_vertices : list of 3-element tuples
            List of vertices from RefinableIcosahedron

        Examples
        --------
        >>> grid = DualIcosphereGraph()
        >>> grid.number_of_nodes
        12
        """
        nverts = len(ico_vertices)
        self.coords_of_node = np.zeros((nverts, 3))
        self.x_of_node = self.coords_of_node[:, 0]
        self.y_of_node = self.coords_of_node[:, 1]
        self.z_of_node = self.coords_of_node[:, 2]
        self.number_of_nodes = nverts
        for i in range(nverts):
            vtx = ico_vertices[i]
            self.x_of_node[i] = vtx[0]
            self.y_of_node[i] = vtx[1]
            self.z_of_node[i] = vtx[2]

    def add_link(self, p1, p2):
        """
        Add a link between p1 and p2 to a temperatory list of links,
        if it doesn't already exist.
        """
        key = (min(p1, p2) << 32) + max(p1, p2)
        if not (key in self.links):
            # print(" adding link", min(p1, p2), max(p1, p2))
            self.links[key] = (p1, p2)
        # else:
        #    print(" link", min(p1, p2), max(p1, p2), "already exists")

    def setup_links(self, ico_faces):
        """
        Set up link-related data structures.

        Examples
        --------
        >>> ico = DualIcosphereGraph()
        >>> ico.number_of_links
        30
        """
        self.links = {}
        self.nodes_at_link = np.zeros((int(1.5 * len(ico_faces)), 2), dtype=int)
        self.links_at_node = np.zeros((self.number_of_nodes, 6), dtype=int) - 1
        self.link_dirs_at_node = np.zeros((self.number_of_nodes, 6), dtype=int)
        link_at_node_index = np.zeros(self.number_of_nodes, dtype=int)
        for icoface in ico_faces:
            # print("face", icoface)
            self.add_link(icoface[0], icoface[1])
            self.add_link(icoface[1], icoface[2])
            self.add_link(icoface[2], icoface[0])
        i = 0
        self.number_of_links = len(self.links)
        self.length_of_link = np.zeros(self.number_of_links)
        for link in self.links.values():
            tail = link[0]
            # print("Tail of link", i, "is", tail)
            # print(" it is link number", link_at_node_index[tail], "for this node")
            self.nodes_at_link[i, 0] = tail
            self.links_at_node[tail, link_at_node_index[tail]] = i
            self.link_dirs_at_node[tail, link_at_node_index[tail]] = -1
            link_at_node_index[tail] += 1
            head = link[1]
            # print("Head of link", i, "is", head)
            # print(" it is link number", link_at_node_index[head], "for this node")
            self.nodes_at_link[i, 1] = head
            self.links_at_node[head, link_at_node_index[head]] = i
            self.link_dirs_at_node[head, link_at_node_index[head]] = 1
            link_at_node_index[head] += 1
            self.length_of_link[i] = self.radius * arc_length(
                self.coords_of_node[tail], self.coords_of_node[head], self.radius
            )
            i += 1
        self.node_at_link_tail = self.nodes_at_link[:, 0]
        self.node_at_link_head = self.nodes_at_link[:, 1]
        # print("There are", len(self.links), "links")

    @property
    def cell_at_node(self):
        try:
            return self._cell_at_node
        except AttributeError:
            self._cell_at_node = np.arange(self.number_of_nodes, dtype=int)
            return self._cell_at_node

    @property
    def node_at_cell(self):
        return self.cell_at_node

    @property
    def face_at_link(self):
        try:
            return self._face_at_link
        except AttributeError:
            self._face_at_link = np.arange(self.number_of_links, dtype=int)
            return self._face_at_link

    @property
    def link_at_face(self):
        return self.face_at_link

    @property
    def patches_at_node(self):
        return self.corners_at_node

    @property
    def corners_at_cell(self):
        return self.corners_at_node

    @property
    def faces_at_cell(self):
        """Face-cell and node-link numbering are the same!"""
        return self.links_at_node

    def set_coords_of_corner(self):
        """
        Examples
        --------
        >>> import numpy as np
        >>> ico = DualIcosphereGraph()
        >>> ico.x_of_corner**2 + ico.y_of_corner**2 + ico.z_of_corner**2
        array([ 1.,  1.,  1.,  1.,  1.,  1.,  1.,  1.,  1.,  1.,  1.,  1.,  1.,
                1.,  1.,  1.,  1.,  1.,  1.,  1.])
        """

        # print("SCOC HERE")
        # coords of first, second, and third points of triangular patches
        p0 = self.coords_of_node[self.nodes_at_patch[:, 0]]
        p1 = self.coords_of_node[self.nodes_at_patch[:, 1]]
        p2 = self.coords_of_node[self.nodes_at_patch[:, 2]]

        U = p1 - p0  # one side of each tri
        V = p2 - p0  # another side of each tri

        self.coords_of_corner = np.cross(U, V)  # cross-product gives normal vector
        self.x_of_corner = self.coords_of_corner[:, 0]
        self.y_of_corner = self.coords_of_corner[:, 1]
        self.z_of_corner = self.coords_of_corner[:, 2]
        veclen = np.sqrt(
            self.x_of_corner**2 + self.y_of_corner**2 + self.z_of_corner**2
        )  # this is the vector length...
        # print("vl bef", veclen)
        for i in range(3):
            self.coords_of_corner[:, i] *= (
                self.radius / veclen
            )  # ... which we use to normalize
        veclen = np.sqrt(
            self.x_of_corner**2 + self.y_of_corner**2 + self.z_of_corner**2
        )  # this is the vector length...
        # print("vl aft", veclen)

    def setup_patches_and_corners(self, ico_faces):
        """
        Notes
        -----
        Landlab *patches* are the same as what the original algorithm/code
        calls "faces": the triangles that have *nodes* as vertices and
        *links* as edges.

        We assume that the corners are the unit normals of the triangular
        patches (which the original algorithm calls faces), rescaled for
        the given radius.

        Examples
        --------
        >>> import numpy as np
        >>> ico = DualIcosphereGraph()
        >>> ico.number_of_corners
        20
        >>> ico.number_of_patches
        20
        >>> ico.nodes_at_patch[0]
        array([ 0, 11,  5])
        >>> ico.corners_at_node[1]
        array([ 2,  1,  5, 19,  9, -1])
        >>> ico.patches_at_node[1]
        array([ 2,  1,  5, 19,  9, -1])
        """
        self.number_of_corners = len(ico_faces)
        self.number_of_patches = self.number_of_corners

        # Nodes at patch and corners at node
        self.nodes_at_patch = np.zeros((self.number_of_patches, 3), dtype=int)
        self.corners_at_node = -np.ones((self.number_of_nodes, 6), dtype=int)
        corners_at_node_index = np.zeros(self.number_of_nodes, dtype=int)
        for p in range(self.number_of_patches):
            self.nodes_at_patch[p, :] = np.array(ico_faces[p])
            # print("Patch", p, "has nodes", self.nodes_at_patch[p, :])
            for node in self.nodes_at_patch[p, :]:
                self.corners_at_node[node, corners_at_node_index[node]] = p
                corners_at_node_index[node] += 1
        # print("Corners at node:")
        # print(self.corners_at_node)
        self.set_coords_of_corner()
        self.sort_corners_ccw()

    def _calc_area_of_patch(self):
        """Calculate and return the surface area of the spherical triangular patches."""
        pass

    @property
    def area_of_patch(self):
        try:
            return self._area_of_patch
        except AttributeError:
            self._calc_area_of_patch(self)
            return self._area_of_patch

    @property
    def r_of_node(self):
        try:
            return self._r_of_node
        except AttributeError:
            self._setup_node_spherical_coords()
            return self._r_of_node

    @property
    def phi_of_node(self):
        try:
            return self._phi_of_node
        except AttributeError:
            self._setup_node_spherical_coords()
            return self._phi_of_node

    @property
    def theta_of_node(self):
        try:
            return self._theta_of_node
        except AttributeError:
            self._setup_node_spherical_coords()
            return self._theta_of_node

    def _setup_node_spherical_coords(self):
        (
            self._r_of_node,
            self._phi_of_node,
            self._theta_of_node,
        ) = cartesian_to_spherical(self.x_of_node, self.y_of_node, self.z_of_node)

    def sort_corners_ccw(self):
        """
        Notes
        -----

        The algorithm is:

        FOR EACH NODE
            GET SPHERICAL COORDS R, PHI, THETA
            MAKE A COPY OF CORNER COORDS ROTATED BY -PHI AND -THETA
            FIND ANGLE OF (ROTATED) CORNERS RELATIVE TO NODE IN XY PLANE
            SORT CORNERS AT NODE ACCORDING TO ANGLE

        Examples
        --------
        >>> ico = DualIcosphereGraph()
        >>> ico.corners_at_node[0]
        array([ 3,  4,  0,  1,  2, -1])
        """
        for node in range(self.number_of_nodes):  # can this be vectorized?
            # rotate corners such that node (x,y) = 0
            nc = np.count_nonzero(
                self.corners_at_node[node] + 1
            )  # number of corners at this node (5 or 6)
            cx = self.x_of_corner[self.corners_at_node[node, :nc]]
            cy = self.y_of_corner[self.corners_at_node[node, :nc]]
            cz = self.z_of_corner[self.corners_at_node[node, :nc]]
            rcx, rcy, _ = rotate_zy(
                cx, cy, cz, -self.phi_of_node[node], -self.theta_of_node[node]
            )

            # find angles of vectors node -> each corner
            ang = np.arctan2(rcy, rcx)
            ang[ang < 0.0] += 2 * np.pi

            # sort by angle
            idx = np.argsort(ang)
            self.corners_at_node[node, :nc] = self.corners_at_node[node, idx]

    def setup_cells(self):
        """
        Calculate areas of cells.

        Area calculation uses the fact that cells are either pentagonal or hexagonal.
        Therefore the area can be calculated by first finding the area of a triangle
        formed by the cell's node and the first two of its corners, and then
        multiplying by either 5 or 6. We take advantage of the fact that node and
        cell numbering are the same. We detect shape by looking at the number of
        non-negative (= valid) entries in the corners_at_cell array.

        We could probably just calculate the first hex and first pent, and then
        assign the same area to all others accordingly (TODO).
        """
        self.number_of_cells = self.number_of_nodes
        self.area_of_cell = np.zeros(self.number_of_cells)

        for cell in range(self.number_of_cells):
            p0 = self.coords_of_node[cell]
            p1 = self.coords_of_corner[self.corners_at_node[cell][0]]
            p2 = self.coords_of_corner[self.corners_at_node[cell][1]]
            area_of_tri = area_of_sphertri(p0, p1, p2, self.radius)
            ntri = 5 + int(np.amin(self.corners_at_node[cell]) > -1)
            self.area_of_cell[cell] = ntri * area_of_tri
