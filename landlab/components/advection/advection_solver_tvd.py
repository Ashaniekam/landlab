#!/usr/bin/env python3
"""Solve advection numerically using Total Variation Diminishing method."""

import numpy as np

from landlab import Component, LinkStatus
from landlab.components.advection.flux_limiters import flux_lim_vanleer
from landlab.utils.return_array import return_array_at_node


def find_upwind_link_at_link(grid, u):
    """Return the upwind link at every link.

    For all links, return ID of upwind link, defined based on the sign of `u`.
    If `u` is zero, the upwind link is found as though `u` were positive.

    For instance (see examples below), consider a 3x4 raster grid with link
    numbering::

        .-14-.-15-.-16-.
        |    |    |    |
        10  11   12   13
        |    |    |    |
        .--7-.--8-.--9-.
        |    |    |    |
        3    4    5    6
        |    |    |    |
        .--0-.--1-.--2-.

    There are at most 7 active links (4, 5, 7, 8, 9, 11, 12).
    If `u` is positive everywhere, then the upwind links are::

        .----.-14-.-15-.
        |    |    |    |
        3    4    5    6
        |    |    |    |
        .----.--7-.--8-.
        |    |    |    |
        |    |    |    |
        |    |    |    |
        .----.--0-.--1-.

    If `u` is negative everywhere, then the upwind links are::

        .-15-.-16-.----.
        |    |    |    |
        |    |    |    |
        |    |    |    |
        .--8-.--9-.----.
        |    |    |    |
        10  11   12   13
        |    |    |    |
        .--1-.--2-.----.

    Parameters
    ----------
    grid : ModelGrid
        A landlab grid.
    u : float or (n_links,) ndarray
        Array of *at-link* values used to determine which node is
        upwind.

    Returns
    -------
    (n_links,) ndarray of int
        The upwind links.

    Examples
    --------
    >>> import numpy as np
    >>> from landlab import RasterModelGrid
    >>> grid = RasterModelGrid((3, 4))

    >>> uwl = find_upwind_link_at_link(grid, 1.0)
    >>> uwl[grid.vertical_links].reshape((2, 4))
    array([[-1, -1, -1, -1],
           [ 3,  4,  5,  6]])
    >>> uwl[grid.horizontal_links].reshape((3, 3))
    array([[-1,  0,  1],
           [-1,  7,  8],
           [-1, 14, 15]])

    >>> uwl = find_upwind_link_at_link(grid, -1.0)
    >>> uwl[grid.vertical_links].reshape((2, 4))
    array([[10, 11, 12, 13],
           [-1, -1, -1, -1]])
    >>> uwl[grid.horizontal_links].reshape((3, 3))
    array([[ 1,  2, -1],
           [ 8,  9, -1],
           [15, 16, -1]])

    >>> u = np.zeros(grid.number_of_links)
    >>> u[4:6] = -1
    >>> u[7] = -1
    >>> u[8:10] = 1
    >>> u[11:13] = 1
    >>> u[grid.vertical_links].reshape((2, 4))
    array([[ 0., -1., -1.,  0.],
           [ 0.,  1.,  1.,  0.]])
    >>> u[grid.horizontal_links].reshape((3, 3))
    array([[ 0.,  0.,  0.],
           [-1.,  1.,  1.],
           [ 0.,  0.,  0.]])
    >>> uwl = find_upwind_link_at_link(grid, u)
    >>> uwl[grid.vertical_links].reshape((2, 4))
    array([[-1, 11, 12, -1],
           [ 3,  4, 5,   6]])
    >>> uwl[grid.horizontal_links].reshape((3, 3))
    array([[-1,  0,  1],
           [ 8,  7,  8],
           [-1, 14, 15]])
    """
    pll = grid.parallel_links_at_link

    cols = np.choose(np.broadcast_to(u, len(pll))>=0, [1, 0])
    uwl = pll[np.arange(len(pll)), cols]

    return uwl


def upwind_to_local_grad_ratio(grid, v, uwll, out=None):
    """Calculate and return ratio of upwind to local gradient in v.

    Gradients are defined on links. Upwind is pre-determined via
    parameter uwll (upwind link at link), which can be obtained
    using the find_upwind_link_at_link function.

    In Total Variation Diminishing (TVD) numerical schemes, this
    ratio is input to a flux limiter to calculate the weighting factor
    for higher-order vs. lower-order terms.
    """
    if out is None:
        out = np.ones(grid.number_of_links)
    else:
        out[:] = 1.0

    h = grid.node_at_link_head
    t = grid.node_at_link_tail
    local_diff = v[h] - v[t]
    upwind_exists_and_nonzero_local = np.logical_and(uwll != -1, local_diff != 0.0)
    out[upwind_exists_and_nonzero_local] = (
        local_diff[uwll[upwind_exists_and_nonzero_local]]
        / local_diff[upwind_exists_and_nonzero_local]
    )
    return out


class AdvectionSolverTVD(Component):
    r"""Component that implements numerical solution for advection using a
    Total Variation Diminishing method.

    The component is restricted to regular grids (e.g., Raster or Hex).

    Parameters
    ----------
    grid : RasterModelGrid or HexModelGrid
        A Landlab grid object.
    field_to_advect : field name or (n_nodes,) array (default None)
        A node field of scalar values that will be advected. If not given,
        the component creates a generic field, initialized to zeros,
        called advected__quantity.
    advection_direction_is_steady : bool (default False)
        Indicates whether the directions of advection are expected to remain
        steady throughout a run. If True, some computation time is saved
        by calculating upwind links only once.

    Examples
    --------
    >>> import numpy as np
    >>> from landlab import RasterModelGrid
    >>> from landlab.components import AdvectionSolverTVD
    >>> grid = RasterModelGrid((3, 7))
    >>> s = grid.add_zeros("advected__quantity", at="node")
    >>> s[9:12] = np.array([1.0, 2.0, 1.0])
    >>> u = grid.add_zeros("advection__velocity", at="link")
    >>> u[grid.horizontal_links] = 1.0
    >>> advec = AdvectionSolverTVD(grid, field_to_advect="advected__quantity")
    >>> for _ in range(5):
    ...     advec.update(0.2)
    >>> np.argmax(s[7:14])
    4
    """

    _name = "AdvectionSolverTVD"

    _unit_agnostic = True

    _info = {
        "advected__quantity": {
            "dtype": float,
            "intent": "out",
            "optional": True,
            "units": "-",
            "mapping": "node",
            "doc": "Scalar quantity advected",
        },
        "advection__flux": {
            "dtype": float,
            "intent": "out",
            "optional": False,
            "units": "m2/y",
            "mapping": "link",
            "doc": "Link-parallel advection flux",
        },
        "advection__velocity": {
            "dtype": float,
            "intent": "in",
            "optional": False,
            "units": "m/y",
            "mapping": "link",
            "doc": "Link-parallel advection velocity magnitude",
        },
    }

    def __init__(
        self,
        grid,
        field_to_advect=None,
        advection_direction_is_steady=False,
    ):
        """Initialize AdvectionSolverTVD."""

        # Call base class methods to check existence of input fields,
        # create output fields, etc.
        super().__init__(grid)
        self.initialize_output_fields()

        if field_to_advect is None:
            self._scalar = self.grid.add_zeros("advected__quantity", at="node")
        else:
            self._scalar = return_array_at_node(self.grid, field_to_advect)
        self._vel = self.grid.at_link["advection__velocity"]
        self._flux_at_link = self.grid.at_link["advection__flux"]

        self._advection_direction_is_steady = advection_direction_is_steady
        if advection_direction_is_steady:  # if so, only need to do this once
            self._upwind_link_at_link = find_upwind_link_at_link(self.grid, self._vel)
            self._upwind_link_at_link[self.grid.status_at_link == LinkStatus.INACTIVE] = -1

    def calc_rate_of_change_at_nodes(self, dt):
        """Calculate and return the time rate of change in the advected
        quantity at nodes.

        Parameters
        ----------
        dt : float
            Time-step duration. Needed to calculate the Courant number.
        """
        if not self._advection_direction_is_steady:
            self._upwind_link_at_link = find_upwind_link_at_link(self.grid, self._vel)
            self._upwind_link_at_link[self.grid.status_at_link == LinkStatus.INACTIVE] = -1
        s_link_low = self.grid.map_node_to_link_linear_upwind(self._scalar, self._vel)
        s_link_high = self.grid.map_node_to_link_lax_wendroff(
            self._scalar, dt * self._vel / self.grid.length_of_link
        )
        r = upwind_to_local_grad_ratio(
            self.grid, self._scalar, self._upwind_link_at_link
        )
        psi = flux_lim_vanleer(r)
        s_at_link = psi * s_link_high + (1.0 - psi) * s_link_low
        self._flux_at_link[self.grid.active_links] = (
            self._vel[self.grid.active_links] * s_at_link[self.grid.active_links]
        )
        return -self.grid.calc_flux_div_at_node(self._flux_at_link)

    def update(self, dt):
        """Update the solution by one time step dt (same as run_one_step())."""
        roc = self.calc_rate_of_change_at_nodes(dt)
        self._scalar[self.grid.core_nodes] += roc[self.grid.core_nodes] * dt

    def run_one_step(self, dt):
        """Update the solution by one time step dt (same as update())."""
        self.update(dt)
