#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# utils/distance.py

'''
Functions for measuring distances.
'''

import numpy as np
from pyemd import emd
from scipy.spatial.distance import cdist
from scipy.stats import entropy

from . import config, constants, utils, validate
from .constants import Direction
from .distribution import flatten, marginal_zero

# Load precomputed hamming matrices.
_NUM_PRECOMPUTED_HAMMING_MATRICES = 10
_hamming_matrices = utils.load_data('hamming_matrices',
                                    _NUM_PRECOMPUTED_HAMMING_MATRICES)


# TODO extend to nonbinary nodes
def _hamming_matrix(N):
    '''Return a matrix of Hamming distances for the possible states of |N|
    binary nodes.

    Args:
        N (int): The number of nodes under consideration

    Returns:
        np.ndarray: A |2^N x 2^N| matrix where the |ith| element is the Hamming
        distance between state |i| and state |j|.

    Example:
        >>> _hamming_matrix(2)
        array([[ 0.,  1.,  1.,  2.],
               [ 1.,  0.,  2.,  1.],
               [ 1.,  2.,  0.,  1.],
               [ 2.,  1.,  1.,  0.]])
    '''
    if N < _NUM_PRECOMPUTED_HAMMING_MATRICES:
        return _hamming_matrices[N]
    return _compute_hamming_matrix(N)


@constants.joblib_memory.cache
def _compute_hamming_matrix(N):
    '''
    Compute and store a Hamming matrix for |N| nodes.

    Hamming matrices have the following sizes:

    n   MBs
    ==  ===
    9   2
    10  8
    11  32
    12  128
    13  512

    Given these sizes and the fact that large matrices are needed infrequently,
    we store computed matrices using the Joblib filesystem cache instead of
    adding computed matrices to the ``_hamming_matrices`` global and clogging
    up memory.

    This function is only called when N > _NUM_PRECOMPUTED_HAMMING_MATRICES.
    Don't call this function directly; use :func:`_hamming_matrix` instead.
    '''
    possible_states = np.array(list(utils.all_states((N))))
    return cdist(possible_states, possible_states, 'hamming') * N


# TODO extend to binary nodes
def hamming_emd(d1, d2):
    '''Return the Earth Mover's Distance between two distributions (indexed
    by state, one dimension per node) using the Hamming distance between states
    as the transportation cost function.

    Singleton dimensions are sqeezed out.
    '''
    N = d1.squeeze().ndim
    d1, d2 = flatten(d1), flatten(d2)
    return emd(d1, d2, _hamming_matrix(N))


def effect_emd(d1, d2):
    '''Compute the EMD between two effect repertoires.

    Because the nodes are independent, the EMD between effect repertoires is
    equal to the sum of the EMDs between the marginal distributions of each
    node, and the EMD between marginal distribution for a node is the absolute
    difference in the probabilities that the node is off.

    Args:
        d1 (np.ndarray): The first repertoire.
        d2 (np.ndarray): The second repertoire.

    Returns:
        float: The EMD between ``d1`` and ``d2``.
    '''
    return sum(abs(marginal_zero(d1, i) - marginal_zero(d2, i))
               for i in range(d1.ndim))


def l1(d1, d2):
    '''Return the L1 distance between two distributions.

    Args:
        d1 (np.ndarray): The first distribution.
        d2 (np.ndarray): The second distribution.

    Returns:
        float: The sum of absolute differences of ``d1`` and ``d2``.
    '''
    return np.absolute(d1 - d2).sum()


def kld(d1, d2):
    '''Return the Kullback-Leibler Divergence (KLD) between two distributions.

    Args:
        d1 (np.ndarray): The first distribution.
        d2 (np.ndarray): The second distribution.

    Returns:
        float: The KLD of ``d1`` from ``d2``.
    '''
    d1, d2 = flatten(d1), flatten(d2)
    return entropy(d1, d2, 2.0)


def entropy_difference(d1, d2):
    '''Return the difference in entropy between two distributions.'''
    d1, d2 = flatten(d1), flatten(d2)
    return abs(entropy(d1, base=2.0) - entropy(d2, base=2.0))


def psq2(d1, d2):
    '''Compute the PSQ2 measure.

    Args:
        d1 (np.ndarray): The first distribution.
        d2 (np.ndarray): The second distribution.
    '''
    d1, d2 = flatten(d1), flatten(d2)

    def f(p):
        return sum((p ** 2) * np.nan_to_num(np.log(p * len(p))))

    return abs(f(d1) - f(d2))


def mp2q(p, q):
    '''Compute the MP2Q measure.

    Args:
        p (np.ndarray): The unpartitioned repertoire
        q (np.ndarray): The partitioned repertoire
    '''
    p, q = flatten(p), flatten(q)
    entropy_dist = 1 / len(p)
    return sum(entropy_dist * np.nan_to_num((p ** 2) / q * np.log(p / q)))


#: Dictionary mapping measure names to functions
measure_dict = {
    constants.EMD: hamming_emd,
    constants.KLD: kld,
    constants.L1: l1,
    constants.ENTROPY_DIFFERENCE: entropy_difference,
    constants.PSQ2: psq2,
    constants.MP2Q: mp2q
}

#: All asymmetric measures
ASYMMETRIC_MEASURES = [constants.KLD, constants.MP2Q]


def directional_emd(direction, d1, d2):
    '''Compute the EMD between two repertoires for a given direction.

    The full EMD computation is used for cause repertoires. A fast analytic
    solution is used for effect repertoires.

    Args:
        direction (Direction): |PAST| or |FUTURE|.
        d1 (np.ndarray): The first repertoire.
        d2 (np.ndarray): The second repertoire.

    Returns:
        float: The EMD between ``d1`` and ``d2``, rounded to |PRECISION|.

    Raises:
        ValueError: If ``direction`` is invalid.
    '''
    if direction == Direction.PAST:
        func = hamming_emd
    elif direction == Direction.FUTURE:
        func = effect_emd
    else:
        # TODO: test that ValueError is raised
        validate.direction(direction)

    return round(func(d1, d2), config.PRECISION)


def small_phi_measure(direction, d1, d2):
    '''Compute the distance between two repertoires for the given direction.

    Args:
        direction (Direction): |PAST| or |FUTURE|.
        d1 (np.ndarray): The first repertoire.
        d2 (np.ndarray): The second repertoire.

    Returns:
        float: The distance between ``d1`` and ``d2``, rounded to |PRECISION|.
    '''
    if config.MEASURE == constants.EMD:
        dist = directional_emd(direction, d1, d2)

    elif config.MEASURE in measure_dict:
        dist = measure_dict[config.MEASURE](d1, d2)

    else:
        validate.measure(config.MEASURE)

    # TODO do we actually need to round here?
    return round(dist, config.PRECISION)


def big_phi_measure(r1, r2):
    '''Compute the distance between two repertoires.

    Args:
        r1 (np.ndarray): The first repertoire.
        r2 (np.ndarray): The second repertoire.

    Returns:
        float: The distance between ``r1`` and ``r2``.
    '''
    if config.MEASURE in ASYMMETRIC_MEASURES:
        raise ValueError("{} is not supported as a big-phi measure due to its "
                         "asymmetry.".format(config.MEASURE))

    elif config.MEASURE not in measure_dict:
        validate.measure(config.MEASURE)

    return measure_dict[config.MEASURE](r1, r2)
