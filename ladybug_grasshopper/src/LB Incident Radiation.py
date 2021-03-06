# Ladybug: A Plugin for Environmental Analysis (GPL)
# This file is part of Ladybug.
#
# Copyright (c) 2020, Ladybug Tools.
# You should have received a copy of the GNU General Public License
# along with Ladybug; If not, see <http://www.gnu.org/licenses/>.
# 
# @license GPL-3.0+ <http://spdx.org/licenses/GPL-3.0+>

"""
Calculate the incident radiation on geometry using a sky matrix from the "Cumulative
Sky Matrix" component.
_
Such studies of incident radiation can be used to apprxomiate the energy that can
be collected from photovoltaic or solar thermal systems. They are also useful
for evaluating the impact of a building's windows on both energy use and the
size/cost of cooling systems. For studies of cooling system size/cost, a sky
matrix derived from the STAT file's clear sky radiation should be used. For
studies of energy use impact, such as the evaluation of passive solar heating
or the potential for excessive cooling energy use, a matrix from EPW radiation
should be used.
_
Note that NO REFLECTIONS OF SOLAR ENERGY ARE INCLUDED IN THE ANALYSIS
PERFORMED BY THIS COMPONENT and it is important to bear in mind that vertical
surfaces typically receive 20% - 30% of their solar energy from reflection off
of the ground. Also note that this component uses the CAD environment's ray
intersection methods, which can be fast for geometries with low complexity
but does not scale well for complex geometries or many test points. For such
complex cases and situations where relfection of solar energy are important,
honeybee-radiance should be used.
-

    Args:
        _sky_mtx: A Sky Matrix from the "LB Cumulative Sky Matrix" component, which
            describes the radiation coming from the various patches of the sky.
            The "LB Sky Dome" component can be used to visualize any sky matrix
            to understand its relationship to the test geometry.
        _geometry: Rhino Breps and/or Rhino Meshes for which incident radiation analysis
            will be conducted. If Breps are input, they will be subdivided using
            the _grid_size to yeild individual points at which analysis will
            occur. If a Mesh is input, radiation analysis analysis will be
            performed for each face of this mesh instead of subdividing it.
        context_: Rhino Breps and/or Rhino Meshes representing context geometry
            that can block solar radiation to the test _geometry.
        _grid_size: A positive number in Rhino model units for the size of grid
            cells at which the input _geometry will be subdivided for incident
            radiation analysis. The smaller the grid size, the higher the
            resolution of the analysis and the longer the calculation will take.
            So it is recommended that one start with a large value here and
            decrease the value as needed. However, the grid size should usually
            be smaller than the dimensions of the smallest piece of the _geometry
            and context_ in order to yield meaningful results.
        _offset_dist_: A number for the distance to move points from the surfaces
            of the input _geometry.  Typically, this should be a small positive
            number to ensure points are not blocked by the mesh. (Default: 10 cm
            in the equivalent Rhino Model units).
        legend_par_: Optional legend parameters from the "LB Legend Parameters"
            that will be used to customize the display of the results.
        parallel_: Set to "True" to run the study using multiple CPUs. This can
            dramatically decrease calculation time but can interfere with
            other computational processes that might be running on your
            machine. (Default: False).
        _run: Set to "True" to run the component and perform incident radiation
            analysis.

    Returns:
        report: ...
        points: The grid of points on the test _geometry that are be used to perform
            the incident radiation analysis.
        results: A list of numbers that aligns with the points. Each number indicates
            the cumulative incident radiation received by each of the points
            from the sky matrix in kWh/m2.
        total: A number for the total incident solar energy falling on all input geometry
            in kWh. Note that, unlike the radiation results above, which are
            normlaized by area, these values are not area-normalized and so
            the input geometry must be represented correctly in the Rhino
            model's unit system in order for this output to be meaningful.
        mesh: A colored mesh of the test _geometry representing the cumulative
            incident radiation received by the input _geometry.
        legend: A legend showing the kWh/m2 that correspond to the colors of the mesh.
        title: A text object for the study title.
        int_mtx: A Matrix object that can be connected to the "LB Deconstruct Matrix"
            component to obtain detailed patch-by-patch results of the study.
            Each sub-list of the matrix (aka. branch of the Data Tree) represents
            one of the points used for analysis. The length of each sub-list
            matches the number of sky patches in the input sky matrix (145 for
            the default Tregenza sky and 577 for the high_density Reinhart sky).
            Each value in the sub-list is a value between 0 and 1 indicating the
            relationship between the point and the patch of the sky. A value of
            "0", indicates that the patch is not visible for that point at all
            while a value of "1" indicates that the patch hits the surface that
            the point represents head on.
"""

ghenv.Component.Name = "LB Incident Radiation"
ghenv.Component.NickName = 'IncidentRadiation'
ghenv.Component.Message = '1.0.0'
ghenv.Component.Category = 'Ladybug'
ghenv.Component.SubCategory = '3 :: Analyze Geometry'
ghenv.Component.AdditionalHelpFromDocStrings = '1'

import math
try:  # python 2
    from itertools import izip as zip
except ImportError:  # python 3
    pass

try:
    from ladybug.viewsphere import view_sphere
    from ladybug.graphic import GraphicContainer
except ImportError as e:
    raise ImportError('\nFailed to import ladybug:\n\t{}'.format(e))

try:
    from ladybug_rhino.config import conversion_to_meters
    from ladybug_rhino.togeometry import to_joined_gridded_mesh3d
    from ladybug_rhino.fromgeometry import from_mesh3d, from_point3d, from_vector3d
    from ladybug_rhino.fromobjects import legend_objects
    from ladybug_rhino.text import text_objects
    from ladybug_rhino.intersect import join_geometry_to_mesh, intersect_mesh_rays
    from ladybug_rhino.grasshopper import all_required_inputs, hide_output, \
        show_output, objectify_output, de_objectify_output
except ImportError as e:
    raise ImportError('\nFailed to import ladybug_rhino:\n\t{}'.format(e))


if all_required_inputs(ghenv.Component) and _run:
        # set the default offset distance
        _offset_dist_ = _offset_dist_ if _offset_dist_ is not None \
            else 0.1 / conversion_to_meters()

        # create the gridded mesh from the geometry
        study_mesh = to_joined_gridded_mesh3d(_geometry, _grid_size, _offset_dist_)
        points = [from_point3d(pt) for pt in study_mesh.face_centroids]
        hide_output(ghenv.Component, 1)

        # mesh the geometry and context
        shade_mesh = join_geometry_to_mesh(_geometry + context_)

        # deconstruct the matrix and get the sky dome vectors
        mtx = de_objectify_output(_sky_mtx)
        total_sky_rad = [dir_rad + dif_rad for dir_rad, dif_rad in zip(mtx[1], mtx[2])]
        lb_vecs = view_sphere.tregenza_dome_vectors if len(total_sky_rad) == 145 \
            else view_sphere.reinhart_dome_vectors
        if mtx[0][0] != 0:  # there is a north input for sky; rotate vectors
            north_angle = math.radians(mtx[0][0])
            lb_vecs = [vec.rotate_xy(north_angle) for vec in lb_vecs]
        sky_vecs = [from_vector3d(vec) for vec in lb_vecs]

        # intersect the rays with the mesh
        normals = [from_vector3d(vec) for vec in study_mesh.face_normals]
        int_matrix_init, angles = intersect_mesh_rays(
            shade_mesh, points, sky_vecs, normals, parallel=parallel_)

        # compute the results
        results = []
        int_matrix = []
        for int_vals, angles in zip(int_matrix_init, angles):
            pt_rel = [ival * math.cos(ang) for ival, ang in zip(int_vals, angles)]
            int_matrix.append(pt_rel)
            rad_result = sum(r * w for r, w in zip(pt_rel, total_sky_rad))
            results.append(rad_result)

        # output the intersection matrix and compute total radiation
        int_mtx = objectify_output('Geometry/Sky Intersection Matrix', int_matrix)
        unit_conv = conversion_to_meters() ** 2
        total = 0
        for rad, area in zip(results, study_mesh.face_areas):
            total += rad * area * unit_conv

        # create the mesh and legend outputs
        graphic = GraphicContainer(results, study_mesh.min, study_mesh.max, legend_par_)
        graphic.legend_parameters.title = 'kWh/m2'
        title = text_objects(
            'Incident Radiation', graphic.lower_title_location,
            graphic.legend_parameters.text_height * 1.5,
            graphic.legend_parameters.font)

        # create all of the visual outputs
        study_mesh.colors = graphic.value_colors
        mesh = from_mesh3d(study_mesh)
        legend = legend_objects(graphic.legend)
