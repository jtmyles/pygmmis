from __future__ import division
import numpy as np
import ctypes

def createShared(a, dtype=ctypes.c_double):
    """Create a shared array to be used for multiprocessing's processes.

    Taken from http://stackoverflow.com/questions/5549190/

    Works only for float, double, int, long types (e.g. no bool).

    Args:
        numpy array, arbitrary shape

    Returns:
        numpy array whose container is a multiprocessing.Array
    """
    import multiprocessing
    shared_array_base = multiprocessing.Array(dtype, a.size)
    shared_array = np.ctypeslib.as_array(shared_array_base.get_obj())
    shared_array[:] = a.flatten()
    shared_array = shared_array.reshape(a.shape)
    return shared_array

# this is to allow multiprocessing pools to operate on class methods:
# https://gist.github.com/bnyeggen/1086393
def _pickle_method(method):
	func_name = method.im_func.__name__
	obj = method.im_self
	cls = method.im_class
	if func_name.startswith('__') and not func_name.endswith('__'): #deal with mangled names
		cls_name = cls.__name__.lstrip('_')
		func_name = '_' + cls_name + func_name
	return _unpickle_method, (func_name, obj, cls)

def _unpickle_method(func_name, obj, cls):
	for cls in cls.__mro__:
		try:
			func = cls.__dict__[func_name]
		except KeyError:
			pass
		else:
			break
	return func.__get__(obj, cls)

import copy_reg
import types
copy_reg.pickle(types.MethodType, _pickle_method, _unpickle_method)


# Blantant copy from Erin Sheldon's esutil
# https://github.com/esheldon/esutil/blob/master/esutil/numpy_util.py
def match1d(arr1input, arr2input, presorted=False):
    """
    NAME:
        match
    CALLING SEQUENCE:
        ind1,ind2 = match(arr1, arr2, presorted=False)
    PURPOSE:
        Match two numpy arrays.  Return the indices of the matches or empty
        arrays if no matches are found.  This means arr1[ind1] == arr2[ind2] is
        true for all corresponding pairs.  arr1 must contain only unique
        inputs, but arr2 may be non-unique.
        If you know arr1 is sorted, set presorted=True and it will run
        even faster
    METHOD:
        uses searchsorted with some sugar.  Much faster than old version
        based on IDL code.
    REVISION HISTORY:
        Created 2015, Eli Rykoff, SLAC.
    """

    # make sure 1D
    arr1 = np.array(arr1input, ndmin=1, copy=False)
    arr2 = np.array(arr2input, ndmin=1, copy=False)

    # check for integer data...
    if (not issubclass(arr1.dtype.type,np.integer) or
        not issubclass(arr2.dtype.type,np.integer)) :
        mess="Error: only works with integer types, got %s %s"
        mess = mess % (arr1.dtype.type,arr2.dtype.type)
        raise ValueError(mess)

    if (arr1.size == 0) or (arr2.size == 0) :
        mess="Error: arr1 and arr2 must each be non-zero length"
        raise ValueError(mess)

    # make sure that arr1 has unique values...
    test=np.unique(arr1)
    if test.size != arr1.size:
        raise ValueError("Error: the arr1input must be unique")

    # sort arr1 if not presorted
    if not presorted:
        st1 = np.argsort(arr1)
    else:
        st1 = None

    # search the sorted array
    sub1=np.searchsorted(arr1,arr2,sorter=st1)

    # check for out-of-bounds at the high end if necessary
    if (arr2.max() > arr1.max()) :
        bad,=np.where(sub1 == arr1.size)
        sub1[bad] = arr1.size-1

    if not presorted:
        sub2,=np.where(arr1[st1[sub1]] == arr2)
        sub1=st1[sub1[sub2]]
    else:
        sub2,=np.where(arr1[sub1] == arr2)
        sub1=sub1[sub2]

    return sub1,sub2


def logsum(logX, axis=0):
    """Computes log of the sum along give axis from the log of the summands.

    This method tries hard to avoid over- or underflow.
    See appendix A of Bovy, Hogg, Roweis (2009).

    Args:
        logX: numpy array of logarithmic summands
        axis (int): axis to sum over

    Returns:
        log of the sum, shortened by one axis

    Throws:
        ValueError if logX has length 0 along given axis

    """
    floatinfo = np.finfo(logX.dtype)
    underflow = np.log(floatinfo.tiny) - logX.min(axis=axis)
    overflow = np.log(floatinfo.max) - logX.max(axis=axis) - np.log(logX.shape[axis])
    c = np.where(underflow < overflow, underflow, overflow)
    # adjust the shape of c for addition with logX
    c_shape = [slice(None) for i in xrange(len(logX.shape))]
    c_shape[axis] = None
    return np.log(np.exp(logX + c[c_shape]).sum(axis=axis)) - c


def chi2_cutoff(D, cutoff=3.):
    """D-dimensional eqiuvalent of "n sigma" cut.

    Evaluates the quantile function of the chi-squared distribution to determine
    the limit for the chi^2 of samples wrt to GMM so that they satisfy the
    68-95-99.7 percent rule of the 1D Normal distribution.

    Args:
        D (int): dimensions of the feature space
        cutoff (float): 1D equivalent cut [in units of sigma]

    Returns:
        float: upper limit for chi-squared in D dimensions
    """
    import scipy.stats
    cdf_1d = scipy.stats.norm.cdf(cutoff)
    confidence_1d = 1-(1-cdf_1d)*2
    cutoff_nd = scipy.stats.chi2.ppf(confidence_1d, D)
    return cutoff_nd


class GMM(object):
    """Gaussian mixture model with K components in D dimensions.

    Attributes:
        amp: numpy array (K,), component amplitudes
        mean: numpy array (K,D), component means
        covar: numpy array (K,D,D), component covariances
    """
    def __init__(self, K=0, D=0):
        """Create the arrays for amp, mean, covar."""
        self.amp = np.zeros((K))
        self.mean = np.empty((K,D))
        self.covar = np.empty((K,D,D))

    @property
    def K(self):
        """int: number of components, depends on size of amp."""
        return self.amp.size

    @property
    def D(self):
        """int: dimensions of the feature space."""
        return self.mean.shape[1]

    def save(self, filename, **kwargs):
        """Save GMM to file.

        Args:
            filename (str): name for saved file, should end on .npz as the default
                of numpy.savez(), which is called here
            kwargs:  dictionary of additional information to be stored in file.

        Returns:
            None
        """
        np.savez(filename, amp=self.amp, mean=self.mean, covar=self.covar, **kwargs)

    def load(self, filename):
        """Load GMM from file.

        Additional arguments stored by save() will be ignored.

        Args:
            filename (str): name for file create with save().

        Returns:
            None
        """
        F = np.load(filename)
        self.amp = F["amp"]
        self.mean = F["mean"]
        self.covar = F["covar"]
        F.close()

    def draw(self, size=1, rng=np.random):
        """Draw samples from the GMM.

        Args:
            size (int): number of samples to draw
            rng: numpy.random.RandomState for deterministic draw

        Returns:
            numpy array (size,D)
        """
        # draw indices for components given amplitudes, need to make sure: sum=1
        ind = rng.choice(self.K, size=size, p=self.amp/self.amp.sum())
        N = np.bincount(ind, minlength=self.K)

        # for each component: draw as many points as in ind from a normal
        samples = np.empty((size, self.D))
        lower = 0
        for k in np.flatnonzero(N):
            upper = lower + N[k]
            samples[lower:upper, :] = rng.multivariate_normal(self.mean[k], self.covar[k], size=N[k])
            lower = upper
        return samples

    def __call__(self, coords, covar=None, as_log=False):
        """Evaluate model PDF at given coordinates.

        see logL() for details.

        Args:
            coords: numpy array (D,) or (N, D) of test coordinates
            covar:  numpy array (D, D) or (N, D, D) covariance matrix of coords
            as_log (bool): return log(p) instead p

        Returns:
            numpy array (1,) or (N, 1) of PDF (or its log)
        """
        if as_log:
            return self.logL(coords, covar=covar)
        else:
            return np.exp(self.logL(coords, covar=covar))

    def _mp_chunksize(self):
        # find how many components to distribute over available threads
        import multiprocessing
        cpu_count = multiprocessing.cpu_count()
        chunksize = max(1, self.K//cpu_count)
        n_chunks = min(cpu_count, self.K//chunksize)
        return n_chunks, chunksize

    def _get_chunks(self):
        # split all component in ideal-sized chunks
        n_chunks, chunksize = self._mp_chunksize()
        left = self.K - n_chunks*chunksize
        chunks = []
        n = 0
        for i in xrange(n_chunks):
            n_ = n + chunksize
            if left > i:
                n_ += 1
            chunks.append((n, n_))
            n = n_
        return chunks

    def logL(self, coords, covar=None):
        """Log-likelihood of coords given all (i.e. the sum of) GMM components

        Distributes computation over all threads on the machine.

        If covar is None, this method returns
            log(sum_k(p(x | k)))
        of the data values x. If covar is set, the method returns
            log(sum_k(p(y | k))),
        where y = x + noise and noise ~ N(0, covar).

        Args:
            coords: numpy array (D,) or (N, D) of test coordinates
            covar:  numpy array (D, D) or (N, D, D) covariance matrix of coords

        Returns:
            numpy array (1,) or (N, 1) log(L), depending on shape of data
        """
        # Instead log p (x | k) for each k (which is huge)
        # compute it in stages: first for each chunk, then sum over all chunks
        import multiprocessing
        pool = multiprocessing.Pool()
        chunks = self._get_chunks()
        results = [pool.apply_async(self._logsum_chunk, (chunk, coords, covar)) for chunk in chunks]
        log_p_y_chunk = []
        for r in results:
            log_p_y_chunk.append(r.get())
        pool.close()
        return logsum(np.array(log_p_y_chunk)) # sum over all chunks = all k

    def _logsum_chunk(self, chunk, coords, covar=None):
        # helper function to reduce the memory requirement of logL
        log_p_y_k = np.empty((chunk[1]-chunk[0], len(coords)))
        for i in xrange(chunk[1] - chunk[0]):
            k = chunk[0] + i
            log_p_y_k[i,:] = self.logL_k(k, coords, covar=covar)
        return logsum(log_p_y_k)

    def logL_k(self, k, coords, covar=None, chi2_only=False):
        """Log-likelihood of coords given only component k.

        Args:
            k (int): component index
            coords: numpy array (D,) or (N, D) of test coordinates
            covar:  numpy array (D, D) or (N, D, D) covariance matrix of coords
            chi2_only (bool): only compute deltaX^T Sigma_k^-1 deltaX

        Returns:
            numpy array (1,) or (N, 1) log(L), depending on shape of data
        """
        # compute p(x | k)
        dx = coords - self.mean[k]
        if covar is None:
            T_k = self.covar[k]
        else:
            T_k = self.covar[k] + covar
        chi2 = np.einsum('...i,...ij,...j', dx, np.linalg.inv(T_k), dx)

        if chi2_only:
            return chi2

        # prevent tiny negative determinants to mess up
        (sign, logdet) = np.linalg.slogdet(T_k)
        log2piD2 = np.log(2*np.pi)*(0.5*self.D)
        return np.log(self.amp[k]) - log2piD2 - sign*logdet/2 - chi2/2

class Background(object):
    """Background object to be used in conjuction with GMM.

    For a normalizable uniform distribution, a support footprint must be set.
    It should be sufficiently large to explain all non-clusters samples.

    Attributes:
        amp (float): mixing amplitude
        footprint: numpy array, (D,2) of rectangular volume
        adjust_amp (bool): whether amp will be adjusted as part of the fit
        amp_max (float): maximum value of amp allowed if adjust_amp=True
    """
    def __init__(self, footprint):
        """Initialize Background with a footprint.

        Args:
            footprint: numpy array, (D,2) of rectangular volume

        Returns:
            None
        """
        self.amp = 0
        self.footprint = footprint
        self.adjust_amp = True
        self.amp_max = 1

    @property
    def p(self):
        """Probability of the background model.

        Returns:
            float, equal to 1/volume, where volume is given by footprint.
        """
        volume = np.prod(self.footprint[1] - self.footprint[0])
        return 1/volume

    def draw(self, size=1, rng=np.random):
        """Draw samples from uniform background.

        Args:
            size (int): number of samples to draw
            rng: numpy.random.RandomState for deterministic draw

        Returns:
            numpy array (size, D)
        """
        dx = self.footprint[1] - self.footprint[0]
        return self.footprint[0] + dx*rng.rand(size,len(self.footprint[0]))


############################
# Begin of fit functions
############################

#: Verbosity level: [0,1,2]
VERBOSITY = False
#: Oversampling used for imputation sample, as large as feasible
OVERSAMPLING = 4

def initFromDataMinMax(gmm, data, covar=None, s=None, k=None, rng=np.random):
    """Initialization callback for uniform random component means.

    Component amplitudes are set at 1/gmm.K, covariances are set to
    s**2*np.eye(D), and means are distributed randomly over the range that is
    covered by data.

    If s is not given, it will be set such that the volume of all components
    completely fills the space covered by data.

    Args:
        gmm: A GMM to be initialized
        data: numpy array (N,D) to define the range of the component means
        covar: ignored in this callback
        s (float): if set, sets component variances
        k (iterable): list of components to set, is None sets all components
        rng: numpy.random.RandomState for deterministic behavior

    Returns:
        None
    """
    if k is None:
        k = slice(None)
    gmm.amp[k] = 1/gmm.K
    # set model to random positions with equally sized spheres within
    # volumne spanned by data
    min_pos = data.min(axis=0)
    max_pos = data.max(axis=0)
    gmm.mean[k,:] = min_pos + (max_pos-min_pos)*rng.rand(gmm.K, gmm.D)
    # if s is not set: use volume filling argument:
    # K spheres of radius s [having volume s^D * pi^D/2 / gamma(D/2+1)]
    # should completely fill the volume spanned by data.
    if s is None:
        from scipy.special import gamma
        vol_data = np.prod(max_pos-min_pos)
        s = (vol_data / gmm.K * gamma(gmm.D*0.5 + 1))**(1/gmm.D) / np.sqrt(np.pi)
        if VERBOSITY >= 2:
            print "initializing spheres with s=%.2f in data domain" % s
    gmm.covar[k,:,:] = s**2 * np.eye(data.shape[1])

def initFromDataAtRandom(gmm, data, covar=None, s=None, k=None, rng=np.random):
    """Initialization callback for component means to follow data on scales > s.

    Component amplitudes are set to 1/gmm.K, covariances are set to
    s**2*np.eye(D). For each mean, a data sample is selected at random, and a
    multivariant Gaussian offset is added, whose variance is given by s**2.

    If s is not given, it will be set such that the volume of all components
    completely fills the space covered by data.

    Args:
        gmm: A GMM to be initialized
        data: numpy array (N,D) to define the range of the component means
        covar: ignored in this callback
        s (float): if set, sets component variances
        k (iterable): list of components to set, is None sets all components
        rng: numpy.random.RandomState for deterministic behavior

    Returns:
        None
    """
    if k is None:
        k = slice(None)
        k_len = gmm.K
    else:
        try:
            k_len = len(gmm.amp[k])
        except TypeError:
            k_len = 1
    gmm.amp[k] = 1/gmm.K
    # initialize components around data points with uncertainty s
    refs = rng.randint(0, len(data), size=k_len)
    D = data.shape[1]
    if s is None:
        from scipy.special import gamma
        min_pos = data.min(axis=0)
        max_pos = data.max(axis=0)
        vol_data = np.prod(max_pos-min_pos)
        s = (vol_data / gmm.K * gamma(gmm.D*0.5 + 1))**(1/gmm.D) / np.sqrt(np.pi)
        if VERBOSITY >= 2:
            print "initializing spheres with s=%.2f near data points" % s
    gmm.mean[k,:] = data[refs] + rng.multivariate_normal(np.zeros(D), s**2 * np.eye(D), size=k_len)
    gmm.covar[k,:,:] = s**2 * np.eye(data.shape[1])

# Run a simple GMM to initialize a tricky one:
def initFromSimpleGMM(gmm, data, covar=None, s=None, k=None, rng=np.random, init_callback=initFromDataAtRandom, w=0., cutoff=None, background=None, tol=1e-3, covar_factor=1.):
    """Initialization callback to daisy-chain GMM fits.

    Component amplitudes are first initialized with init_callback, then fit()
    is run with the parameters (w, cutoff, background, tol) as specified.
    Once done, the covariances are multiplied with covar_factor.

    Args:
        gmm: A GMM to be initialized
        data: numpy array (N,D) to define the range of the component means
        covar: data covariance, passed on to fit()
        s (float): if set, sets component variances
        k (iterable): list of components to set, is None sets all components
        rng: numpy.random.RandomState for deterministic behavior
        init_callback: initialization callback for first fit() run
    Returns:
        None
    """
    # 1) run GMM without error and selection (fit is essentially an init fct)
    fit(gmm, data, covar=None, w=w, cutoff=cutoff, sel_callback=None, init_callback=init_callback, background=background, tol=tol, rng=rng)
    # 2) adjust the covariance to allow to provide more support
    # in missing volume
    gmm.covar[:,:,:] *= covar_factor

    # if k is set: only use fit init for given k, re-init the others
    if k is not None:
        k_ = set(range(gmm.K))
        try:
            k_len = len(gmm.amp[k])
            k_ -= set(k)
        except TypeError:
            k_ -= set([k])
        init_callback(gmm, k=k_, data=data, covar=covar, rng=rng)

def initFromKMeans(gmm, data, covar=None, rng=np.random):
    """Initialization callback from a k-means clustering run.

    See Algorithm 1 from Bloemer & Bujna (arXiv:1312.5946)
    NOTE: The result of this call are not deterministic even if rng is set
    because scipy.cluster.vq.kmeans2 uses its own initialization.

    Args:
        gmm: A GMM to be initialized
        data: numpy array (N,D) to define the range of the component means
        covar: ignored in this callback
        rng: numpy.random.RandomState for deterministic behavior

    Returns:
        None
    """
    from scipy.cluster.vq import kmeans2
    center, label = kmeans2(data, gmm.K)
    for k in xrange(gmm.K):
        mask = (label == k)
        gmm.amp[k] = mask.sum() / len(data)
        gmm.mean[k,:] = data[mask].mean(axis=0)
        d_m = data[mask] - gmm.mean[k]
        # funny way of saying: for each point i, do the outer product
        # of d_m with its transpose and sum over i
        gmm.covar[k,:,:] = (d_m[:, :, None] * d_m[:, None, :]).sum(axis=0) / len(data)


def fit(gmm, data, covar=None, w=0., cutoff=None, sel_callback=None, covar_callback=None, init_callback=None, background=None, tol=1e-3, split_n_merge=False, rng=np.random):
    """Fit GMM to data.

    If given, init_callback is called to set up the GMM components. Then, the
    EM sequence is repeated until the mean log-likelihood converges within tol.

    VERBOSITY controls output during the EM steps [0,1,2]
    OVERSAMPLING defines the number if imputation samples per data sample.
        Value of 1 is fine but may become instable. Set as high as feasible.

    Note:
        If background is set, it implies cutoff=None.

    Args:
        gmm: an instance if GMM
        data: numpy array (N,D)
        covar: numpy array (N,D,D) or (D,D) if i.i.d.
        w (float): minimum covariance regularization
        cutoff (float): size of component neighborhood [in 1D equivalent sigmas]
        sel_callback: completeness callback to generate imputation samples.
        covar_callback: covariance callback for imputation samples.
            needs to be present if sel_callback and covar are set.
        init_callback: callback to initialize the components
        background: an instance of Background if simultaneous fitting is desired
        tol (float): tolerance for covergence of mean log-likelihood
        split_n_merge (int): number of split & merge attempts
        rng: numpy.random.RandomState for deterministic behavior

    Returns:
        mean log-likelihood (float), component neighborhoods (list of ints)

    Throws:
        RuntimeError for inconsistent argument combinations
    """

    # init components
    if init_callback is not None:
        init_callback(gmm, data=data, covar=covar, rng=rng)
    elif VERBOSITY:
        print("forgoing initialization: hopefully GMM was initialized...")

    # test if callbacks are consistent
    if covar is not None and sel_callback is not None and covar_callback is None:
        raise RuntimeError("covar is set, but covar_callback is None: imputation samples inconsistent")

    # cutoff cannot be used with background due to competing definitions of neighborhood
    if background is not None and cutoff is not None:
        print("adjusting cutoff = None for background model fit")
        cutoff = None

    # set up pool
    import multiprocessing
    pool = multiprocessing.Pool()
    n_chunks, chunksize = gmm._mp_chunksize()

    # sum_k p(x|k) -> S
    # extra precautions for cases when some points are treated as outliers
    # and not considered as belonging to any component
    log_S = createShared(np.zeros(len(data)))  # S = sum_k p(x|k)
    # FIXME: create sheared boolean array results in
    # AttributeError: 'c_bool' object has no attribute '__array_interface__'
    H = np.zeros(len(data), dtype='bool')      # H == 1 for points in the fit
    log_p = [[] for k in xrange(gmm.K)]   # P = p(x|k) for x in U[k]
    T_inv = [None for k in xrange(gmm.K)] # T = covar(x) + gmm.covar[k]
    U = [None for k in xrange(gmm.K)]     # U = {x close to k}

    if VERBOSITY:
        global VERB_BUFFER

    log_L, N, N2 = _EM(gmm, log_p, U, T_inv, log_S, H, data, covar=covar, sel_callback=sel_callback, covar_callback=covar_callback, w=w, pool=pool, chunksize=chunksize, cutoff=cutoff, background=background, tol=tol, rng=rng)

    # should we try to improve by split'n'merge of components?
    # if so, keep backup copy
    gmm_ = GMM(gmm.K, gmm.D)
    while split_n_merge and gmm.K >= 3:

        gmm_.amp[:] = gmm.amp[:]
        gmm_.mean[:] = gmm.mean[:,:]
        gmm_.covar[:,:,:] = gmm.covar[:,:,:]
        U_ = [U[k].copy() for k in xrange(gmm.K)]

        altered, cleanup = _findSNMComponents(gmm, U, log_p, log_S, N+N2, pool=pool, chunksize=chunksize)

        if VERBOSITY:
            print ("merging %d and %d, splitting %d" % tuple(altered))

        # modify components
        _update_snm(gmm, altered, U, N+N2, cleanup)

        # run partial EM on altered components
        # NOTE: for a partial run, we'd only need the change to Log_S from the
        # altered components. However, the neighborhoods can change from _update_snm
        # or because they move, so that operation is ill-defined.
        # Thus, we'll always run a full E-step, which is pretty cheap for
        # converged neighborhood.
        # The M-step could in principle be run on the altered components only,
        # but there seem to be side effects in what I've tried.
        # Similar to the E-step, the imputation step needs to be run on all
        # components, otherwise the contribution of the altered ones to the mixture
        # would be over-estimated.
        # Effectively, partial runs are as expensive as full runs.
        log_L_, N_, N2_ = _EM(gmm, log_p, U, T_inv, log_S, H, data, covar=covar, sel_callback=sel_callback, covar_callback=covar_callback, w=w, pool=pool, chunksize=chunksize, cutoff=cutoff, background=background, tol=tol, prefix="SNM_P", altered=altered, rng=rng)

        log_L_, N_, N2_ = _EM(gmm, log_p, U, T_inv, log_S, H, data, covar=covar, sel_callback=sel_callback, covar_callback=covar_callback, w=w, pool=pool, chunksize=chunksize, cutoff=cutoff, background=background, tol=tol, prefix="SNM_F", altered=None, rng=rng)

        if log_L >= log_L_:
            # revert to backup
            gmm.amp[:] = gmm_.amp[:]
            gmm.mean[:] = gmm_.mean[:,:]
            gmm.covar[:,:,:] = gmm_.covar[:,:,:]
            U = U_
            if VERBOSITY:
                print ("split'n'merge likelihood decreased: reverting to previous model")
            break

        log_L = log_L_
        split_n_merge -= 1

    pool.close()
    return log_L, U

# run EM sequence
def _EM(gmm, log_p, U, T_inv, log_S, H, data, covar=None, sel_callback=None, covar_callback=None, background=None, w=0, pool=None, chunksize=1, cutoff=None, tol=1e-3, prefix="", altered=None, rng=np.random):

    # compute effective cutoff for chi2 in D dimensions
    if cutoff is not None:
        # note: subsequently the cutoff parameter, e.g. in _E(), refers to this:
        # chi2 < cutoff,
        # while in fit() it means e.g. "cut at 3 sigma".
        # These differing conventions need to be documented well.
        cutoff_nd = chi2_cutoff(gmm.D, cutoff=cutoff)

        # store chi2 cutoff for component shifts, use 0.5 sigma
        shift_cutoff = chi2_cutoff(gmm.D, cutoff=min(0.25, cutoff/2))
    else:
        cutoff_nd = None
        shift_cutoff = chi2_cutoff(gmm.D, cutoff=0.25)

    it = 0
    maxiter = max(100, gmm.K)
    if VERBOSITY:
        global VERB_BUFFER
        print("\nITER\tPOINTS\tIMPUTED\tORIG\tLOG_L\tSTABLE")

    # save backup
    gmm_ = GMM(gmm.K, gmm.D)
    gmm_.amp[:] = gmm.amp[:]
    gmm_.mean[:,:] = gmm.mean[:,:]
    gmm_.covar[:,:,:] = gmm.covar[:,:,:]
    N0 = len(data) # size of original (unobscured) data set (signal and background)
    N2 = 0         # size of imputed signal sample

    while it < maxiter: # limit loop in case of slow convergence

        log_L_, N, N2, N0 = _EMstep(gmm, log_p, U, T_inv, log_S, H, N0, data, covar=covar, sel_callback=sel_callback, covar_callback=covar_callback, background=background, w=w, pool=pool, chunksize=chunksize, cutoff=cutoff_nd, tol=tol, altered=altered, it=it, rng=rng)

        # check if component has moved by more than sigma/2
        shift2 = np.einsum('...i,...ij,...j', gmm.mean - gmm_.mean, np.linalg.inv(gmm_.covar), gmm.mean - gmm_.mean)
        moved = np.flatnonzero(shift2 > shift_cutoff)

        if VERBOSITY:
            print("%s%d\t%d\t%d\t%d\t%.3f\t%d" % (prefix, it, N, N2, N0, log_L_, gmm.K - moved.size))

        # convergence tests:
        if it > 0 and log_L_ < log_L + tol:
            # with imputation or background fitting, observed logL can decrease
            # allow some slack, but revert to previous model if it gets worse
            if log_L_ < log_L - tol:
                gmm.amp[:] = gmm_.amp[:]
                gmm.mean[:,:] = gmm_.mean[:,:]
                gmm.covar[:,:,:] = gmm_.covar[:,:,:]
                if VERBOSITY:
                    print("likelihood decreased: reverting to previous model")
                break
            elif moved.size == 0:
                log_L = log_L_
                if VERBOSITY:
                    print ("likelihood converged within tolerance %r: stopping here." % tol)
                break

        # force update to U for all moved components
        if cutoff is not None:
            for k in moved:
                U[k] = None

        if VERBOSITY >= 2 and moved.size:
            print ("resetting neighborhoods of moving components: (" + ("%d," * moved.size + ")") % tuple(moved))

        # update all important _ quantities for convergence test(s)
        log_L = log_L_
        # backup to see if components move or if next step gets worse
        # note: not gmm = gmm_ !
        gmm_.amp[:] = gmm.amp[:]
        gmm_.mean[:,:] = gmm.mean[:,:]
        gmm_.covar[:,:,:] = gmm.covar[:,:,:]

        it += 1

    if VERBOSITY:
        print ("")

    return log_L, N, N2

# run one EM step
def _EMstep(gmm, log_p, U, T_inv, log_S, H, N0, data, covar=None, sel_callback=None, covar_callback=None, background=None, w=0, pool=None, chunksize=1, cutoff=None, tol=1e-3, altered=None, it=0, rng=np.random):

    log_L = _Estep(gmm, log_p, U, T_inv, log_S, H, data, covar=covar, background=background, pool=pool, chunksize=chunksize, cutoff=cutoff, it=it)
    A,M,C,N,B = _Mstep(gmm, U, log_p, T_inv, log_S, H, data, covar=covar, cutoff=cutoff, background=background, pool=pool, chunksize=chunksize)

    A2 = M2 = C2 = B2 = H2 = N2 = 0

    # here the magic happens: imputation from the current model
    if sel_callback is not None:

        # create fake data with same mechanism as the original data,
        # but invert selection to get the missing part
        data2, covar2, N0 = draw(gmm, len(data)*OVERSAMPLING, sel_callback=sel_callback, orig_size=N0*OVERSAMPLING, invert_sel=True, covar_callback=covar_callback, background=background, rng=rng)
        U2 = [None for k in xrange(gmm.K)]
        N0 = int(N0/OVERSAMPLING)

        if len(data2) > 0:
            log_S2 = np.zeros(len(data2))
            H2 = np.zeros(len(data2), dtype='bool')
            log_p2 = [[] for k in xrange(gmm.K)]
            T2_inv = [None for k in xrange(gmm.K)]

            log_L2 = _Estep(gmm, log_p2, U2, T2_inv, log_S2, H2, data2, covar=covar2, background=background, pool=pool, chunksize=chunksize, cutoff=cutoff, it=it)
            A2,M2,C2,N2,B2 = _Mstep(gmm, U2, log_p2, T2_inv, log_S2, H2, data2, covar=covar2, cutoff=cutoff, background=background, pool=pool, chunksize=chunksize)

            # normalize foer oversampling
            A2 /= OVERSAMPLING
            M2 /= OVERSAMPLING
            C2 /= OVERSAMPLING
            B2 /= OVERSAMPLING
            N2 = N2/OVERSAMPLING # need floating point precision in update

            # check which components are predominantly outside selection
            sel_outside = A2 > tol * A
            if VERBOSITY >= 2 and sel_outside.any():
                print ("component inside fractions: " + ("(" + "%.2f," * gmm.K + ")") % tuple(A/(A+A2)))

    _update(gmm, A, M, C, N, B, H, A2, M2, C2, N2, B2, H2, w, altered=altered, background=background)

    return log_L, N, N2, N0

# perform E step calculations.
# If cutoff is set, this will also set the neighborhoods U
def _Estep(gmm, log_p, U, T_inv, log_S, H, data, covar=None, background=None, pool=None, chunksize=1, cutoff=None, it=0, rng=np.random):
    import parmap
    if background is None:
        # compute p(i | k) for each k independently in the pool
        # need S = sum_k p(i | k) for further calculation
        # also N = {i | i in neighborhood[k]} for any k
        log_S[:] = 0
        H[:] = 0
        k = 0
        for log_p[k], U[k], T_inv[k] in \
        parmap.starmap(_Esum, zip(xrange(gmm.K), U), gmm, data, covar, cutoff, pool=pool, chunksize=chunksize):
            log_S[U[k]] += np.exp(log_p[k]) # actually S, not logS
            H[U[k]] = 1
            k += 1

        # need log(S), but since log(0) isn't a good idea, need to restrict to N_
        log_S[H] = np.log(log_S[H])
        log_L = log_S[H].mean()

    # determine which points belong to background:
    # compare uniform background model with GMM,
    # use H to store association to signal vs background
    # that decision conflicts with per-component U's.
    # also, if log_S would only be estimated for the points associated with the
    # signal, it would also underestimated the probabilities under the joint model.
    # Thus, we ignore any cutoff and compute p(x|k) for all x and k
    else:

        # reset signal U
        for k in xrange(gmm.K):
            U[k] = None

        # don't use cutoff and don't update H:
        # for the signal part: set U[k] = H for the M-step
        k = 0
        log_S[:] = 0
        for log_p[k], U[k], T_inv[k] in \
        parmap.starmap(_Esum, zip(xrange(gmm.K), U), gmm, data, covar, None, pool=pool, chunksize=chunksize):
            log_S += np.exp(log_p[k]) # actually S, not logS; need all points here for log_L below
            k += 1

        p_bg = background.amp * background.p
        q_bg = p_bg / (p_bg + (1-background.amp)*log_S)
        H[:] = q_bg < rng.rand(len(data)) # 0.5

        for k in xrange(gmm.K):
            U[k] = H # shallow copy
            log_p[k] = log_p[k][H]
            if T_inv[k] is not None and T_inv[k].shape != (gmm.D, gmm.D):
                T_inv[k] = T_inv[k][H]

        if VERBOSITY:
            print("BG%d\t%d\t%d\t%.3f" % (it, len(H), (H==0).sum(), background.amp))

        log_L = np.log((1-background.amp)*log_S + background.amp * background.p).mean()
        log_S[:] = np.log(log_S[:])

    return log_L

# compute chi^2, and apply selections on component neighborhood based in chi^2
def _Esum(k, U_k, gmm, data, covar=None, cutoff=None):
    # p(x | k) for all x in the vicinity of k
    # determine all points within cutoff sigma from mean[k]
    if U_k is None:
        dx = data - gmm.mean[k]
    else:
        dx = data[U_k] - gmm.mean[k]

    if covar is None:
         T_inv_k = None
         chi2 = np.einsum('...i,...ij,...j', dx, np.linalg.inv(gmm.covar[k]), dx)
    else:
        # with data errors: need to create and return T_ik = covar_i + C_k
        # and weight each datum appropriately
        if covar.shape == (gmm.D, gmm.D): # one-for-all
            T_inv_k = np.linalg.inv(gmm.covar[k] + covar)
        else: # each datum has covariance
            T_inv_k = np.linalg.inv(gmm.covar[k] + covar[U_k].reshape(len(dx), gmm.D, gmm.D))
        chi2 = np.einsum('...i,...ij,...j', dx, T_inv_k, dx)

    # NOTE: close to convergence, we could stop applying the cutoff because
    # changes to U will be minimal
    if cutoff is not None:
        indices = chi2 < cutoff
        chi2 = chi2[indices]
        if covar is not None and covar.shape != (gmm.D, gmm.D):
            T_inv_k = T_inv_k[indices]
        if U_k is None:
            U_k = np.flatnonzero(indices)
        else:
            U_k = U_k[indices]

    # prevent tiny negative determinants to mess up
    (sign, logdet) = np.linalg.slogdet(gmm.covar[k])

    log2piD2 = np.log(2*np.pi)*(0.5*gmm.D)
    return np.log(gmm.amp[k]) - log2piD2 - sign*logdet/2 - chi2/2, U_k, T_inv_k

# get zeroth, first, second moments of the data weighted with p_k(x) avgd over x
def _Mstep(gmm, U, log_p, T_inv, log_S, H, data, covar=None, cutoff=None, background=None, pool=None, chunksize=1):

    # save the M sums from observed data
    A = np.empty(gmm.K)                 # sum for amplitudes
    M = np.empty((gmm.K, gmm.D))        # ... means
    C = np.empty((gmm.K, gmm.D, gmm.D)) # ... covariances
    N = H.sum()
    B = 0

    # perform sums for M step in the pool
    # NOTE: in a partial run, could work on altered components only;
    # however, there seem to be side effects or race conditions
    import parmap
    k = 0
    for A[k], M[k,:], C[k,:,:] in \
    parmap.starmap(_Msums, zip(xrange(gmm.K), U, log_p, T_inv), gmm, data, log_S, pool=pool, chunksize=chunksize):
        k += 1

    if background is not None:
        p_bg = background.amp * background.p
        q_bg = p_bg / (p_bg + (1-background.amp)*np.exp(log_S))
        B = q_bg.sum()

    return A,M,C,N,B

# update component with the moment matrices.
# If altered is set, update only those components and renormalize the amplitudes
def _update(gmm, A, M, C, N, B, H, A2, M2, C2, N2, B2, H2, w, altered=None, background=None):
    # M-step for all components using data (and data2, if non-zero sums are set)

    # partial EM: normal update for mean and covar, but constrained for amp
    if altered is None:
        changed = slice(None)
    else:
        changed = altered

    if altered is None:
        gmm.amp[changed] = (A + A2)[changed] / (N + N2)
    else:
        # Bovy eq. 31
        unaltered = np.in1d(xrange(gmm.K), altered, assume_unique=True, invert=True)
        gmm.amp[altered] = (A + A2)[altered] / (A + A2)[altered].sum() * (1 - (gmm.amp[unaltered]).sum())
    # because of finite precision during the imputation: renormalize
    gmm.amp /= gmm.amp.sum()

    gmm.mean[changed,:] = (M + M2)[changed,:]/(A + A2)[changed,None]
    # minimum covariance term?
    if w > 0:
        # we assume w to be a lower bound of the isotropic dispersion,
        # C_k = w^2 I + ...
        # then eq. 38 in Bovy et al. only ~works for N = 0 because of the
        # prefactor 1 / (q_j + 1) = 1 / (A + 1) in our terminology
        # On average, q_j = N/K, so we'll adopt that to correct.
        w_eff = w**2 * ((N+N2)/gmm.K + 1)
        gmm.covar[changed,:,:] = (C + C2 + w_eff*np.eye(gmm.D)[None,:,:])[changed,:,:] / (A + A2 + 1)[changed,None,None]
    else:
        gmm.covar[changed,:,:] = (C + C2)[changed,:,:] / (A + A2)[changed,None,None]

    # recompute background amplitude;
    # since B is computed over all samples, not just signal portion, need H.size
    if background is not None and background.adjust_amp:
        if H2 is 0:
            background.amp = min(B / H.size, background.amp_max)
        else:
            background.amp = min((B + B2) / (H.size + H2.size), background.amp_max)

# compute moments for the Mstep
def _Msums(k, U_k, log_p_k, T_inv_k, gmm, data, log_S):
    if log_p_k.size:
        # get log_q_ik by dividing with S = sum_k p_ik
        # NOTE:  this modifies log_p_k in place, but is only relevant
        # within this method since the call is parallel and its arguments
        # therefore don't get updated.
        # NOTE: reshape needed when U_k is None because of its
        # implicit meaning as np.newaxis (which would create a 2D array)
        log_p_k -= log_S[U_k].reshape(log_p_k.size)

        # amplitude: A_k = sum_i q_ik
        A_k = np.exp(logsum(log_p_k))

        # in fact: q_ik, but we treat sample index i silently everywhere
        q_k = np.exp(log_p_k)

        # data with errors?
        d = data[U_k].reshape((log_p_k.size, gmm.D))
        if T_inv_k is None:
            # mean: M_k = sum_i x_i q_ik
            M_k = (d * q_k[:,None]).sum(axis=0)

            # covariance: C_k = sum_i (x_i - mu_k)^T(x_i - mu_k) q_ik
            d_m = d - gmm.mean[k]
            # funny way of saying: for each point i, do the outer product
            # of d_m with its transpose, multiply with pi[i], and sum over i
            C_k = (q_k[:, None, None] * d_m[:, :, None] * d_m[:, None, :]).sum(axis=0)
        else:
            # need temporary variables:
            # b_ik = mu_k + C_k T_ik^-1 (x_i - mu_k)
            # B_ik = C_k - C_k T_ik^-1 C_k
            # to replace pure data-driven means and covariances
            d_m = d - gmm.mean[k]
            b_k = gmm.mean[k] + np.einsum('ij,...jk,...k', gmm.covar[k], T_inv_k, d_m)
            M_k = (b_k * q_k[:,None]).sum(axis=0)

            b_k -= gmm.mean[k]
            B_k = gmm.covar[k] - np.einsum('ij,...jk,...kl', gmm.covar[k], T_inv_k, gmm.covar[k])
            C_k = (q_k[:, None, None] * (b_k[:, :, None] * b_k[:, None, :] + B_k)).sum(axis=0)
        return A_k, M_k, C_k
    else:
        return 0,0,0

# draw from the model (+ background) and apply appropriate covariances
def _drawGMM_BG(gmm, size, covar_callback=None, background=None, rng=np.random):
    # draw sample from model, or from background+model
    if background is None:
        data2 = gmm.draw(size, rng=rng)
    else:
        # model is GMM + Background
        bg_size = int(background.amp * size)
        data2 = np.concatenate((gmm.draw(size-bg_size, rng=rng), background.draw(bg_size, rng=rng)))

    # add noise
    # NOTE: When background is set, adding noise is problematic if
    # scattering them out is more likely than in.
    # This can be avoided when the background footprint is large compared to
    # selection region
    if covar_callback is not None:
        covar2 = covar_callback(data2)
        if covar2.shape == (gmm.D, gmm.D): # one-for-all
            noise = rng.multivariate_normal(np.zeros(gmm.D), covar2, size=len(data2))
        else:
            # create noise from unit covariance and then dot with eigenvalue
            # decomposition of covar2 to get a the right noise distribution:
            # n' = R V^1/2 n, where covar = R V R^-1
            # faster than drawing one sample per each covariance
            noise = rng.multivariate_normal(np.zeros(gmm.D), np.eye(gmm.D), size=len(data2))
            val, rot = np.linalg.eigh(covar2)
            noise = np.einsum('...ij,...j', rot, np.sqrt(val)*noise)
        data2 += noise
    else:
        covar2 = None
    return data2, covar2


def draw(gmm, obs_size, sel_callback=None, invert_sel=False, orig_size=None, covar_callback=None, background=None, rng=np.random):
    """Draw from the GMM (and the Background) with noise and selection.

    Draws orig_size samples from the GMM and the Background, if set; calls
    covar_callback if set and applies resulting covariances; the calls
    sel_callback on the (noisy) samples and returns those matching ones.

    If the number is resulting samples is inconsistent with obs_size, i.e.
    outside of the 68 percent confidence limit of a Poisson draw, it will
    update its estimate for the original sample size orig_size.
    An estimate can be provided with orig_size, otherwise it will use obs_size.

    Note:
        If sel_callback is set, the number of returned samples is not
        necessarily given by obs_size.

    Args:
        gmm: an instance if GMM
        obs_size (int): number of observed samples
        sel_callback: completeness callback to generate imputation samples.
        invert_sel (bool): whether to invert the result of sel_callback
        orig_size (int): an estimate of the original size of the sample.
        background: an instance of Background
        covar_callback: covariance callback for imputation samples.
        rng: numpy.random.RandomState for deterministic behavior

    Returns:
        sample: nunmpy array (N_orig, D)
        covar_sample: numpy array (N_orig, D, D) or None of covar_callback=None
        N_orig (int): updated estimate of orig_size if sel_callback is set

    Throws:
        RuntimeError for inconsistent argument combinations
    """

    if orig_size is None:
        orig_size = int(obs_size)

    # draw from model (with background) and add noise.
    # TODO: may want to decide whether to add noise before selection or after
    # Here we do noise, then selection, but this is not fundamental
    data2, covar2 = _drawGMM_BG(gmm, orig_size, covar_callback=covar_callback, background=background, rng=rng)

    # apply selection
    if sel_callback is not None:
        sel2 = sel_callback(data2)

        # check if predicted observed size is consistent with observed data
        # 68% confidence interval for Poisson variate: observed size
        from scipy.stats import chi2
        alpha = 0.32
        lower = 0.5*chi2.ppf(alpha/2, 2*obs_size)
        upper = 0.5*chi2.ppf(1 - alpha/2, 2*obs_size + 2)
        obs_size_ = sel2.sum()
        while obs_size_ > upper or obs_size_ < lower:
            orig_size = int(orig_size / obs_size_ * obs_size)
            data2, covar2 = _drawGMM_BG(gmm, orig_size, covar_callback=covar_callback, background=background, rng=rng)
            sel2 = sel_callback(data2)
            obs_size_ = sel2.sum()

        if invert_sel:
            sel2 = ~sel2
        data2 = data2[sel2]
        if covar_callback is not None and covar2.shape != (gmm.D, gmm.D):
            covar2 = covar2[sel2]

    return data2, covar2, orig_size


def _JS(k, gmm, log_p, log_S, U, A):
    # compute Kullback-Leiber divergence
    log_q_k = log_p[k] - log_S[U[k]]
    return np.dot(np.exp(log_q_k), log_q_k - np.log(A[k]) - log_p[k] + np.log(gmm.amp[k])) / A[k]


def _findSNMComponents(gmm, U, log_p, log_S, N, pool=None, chunksize=1):
    # find those components that are most similar
    JM = np.zeros((gmm.K, gmm.K))
    # compute log_q (posterior for k given i), but use normalized probabilities
    # to allow for merging of empty components
    log_q = [log_p[k] - log_S[U[k]] - np.log(gmm.amp[k]) for k in xrange(gmm.K)]
    for k in xrange(gmm.K):
        # don't need diagonal (can merge), and JM is symmetric
        for j in xrange(k+1, gmm.K):
            # get index list for intersection of U of k and l
            # FIXME: match1d fails if either U is empty
            # SOLUTION: merge empty U, split another
            i_k, i_j = match1d(U[k], U[j], presorted=True)
            JM[k,j] = np.dot(np.exp(log_q[k][i_k]), np.exp(log_q[j][i_j]))
    merge_jk = np.unravel_index(JM.argmax(), JM.shape)
    # if all Us are disjunct, JM is blank and merge_jk = [0,0]
    # merge two smallest components and clean up from the bottom
    cleanup = False
    if merge_jk[0] == 0 and merge_jk[1] == 0:
        global VERBOSITY
        if VERBOSITY >= 2:
            print ("neighborhoods disjunct. merging components %d and %d" % tuple(merge_jk))
        merge_jk = np.argsort(gmm.amp)[:2]
        cleanup = True


    # split the one whose p(x|k) deviate most from current Gaussian
    # ask for the three worst components to avoid split being in merge_jk
    """
    JS = np.empty(gmm.K)
    import parmap
    k = 0
    A = gmm.amp * N
    for JS[k] in \
    parmap.map(_JS, xrange(gmm.K), gmm, log_p, log_S, U, A, pool=pool, chunksize=chunksize):
        k += 1
    """
    # get largest Eigenvalue, weighed by amplitude
    # Large EV implies extended object, which often is caused by coverving
    # multiple clusters. This happes also for almost empty components, which
    # should rather be merged than split, hence amplitude weights.
    # TODO: replace with linalg.eigvalsh, but eigenvalues are not always ordered
    EV = np.linalg.svd(gmm.covar, compute_uv=False)
    JS = EV[:,0] * gmm.amp
    split_l3 = np.argsort(JS)[-3:][::-1]

    # check that the three indices are unique
    altered = np.array([merge_jk[0], merge_jk[1], split_l3[0]])
    if split_l3[0] in merge_jk:
        if split_l3[1] not in merge_jk:
            altered[2] = split_l3[1]
        else:
            altered[2] = split_l3[2]
    return altered, cleanup


def _update_snm(gmm, altered, U, N, cleanup):
    # reconstruct A from gmm.amp
    A = gmm.amp * N

    # update parameters and U
    # merge 0 and 1, store in 0, Bovy eq. 39
    gmm.amp[altered[0]] = gmm.amp[altered[0:2]].sum()
    if not cleanup:
        gmm.mean[altered[0]] = np.sum(gmm.mean[altered[0:2]] * A[altered[0:2]][:,None], axis=0) / A[altered[0:2]].sum()
        gmm.covar[altered[0]] = np.sum(gmm.covar[altered[0:2]] * A[altered[0:2]][:,None,None], axis=0) / A[altered[0:2]].sum()
        U[altered[0]] = np.union1d(U[altered[0]], U[altered[1]])
    else:
        # if we're cleaning up the weakest components:
        # merging does not lead to valid component parameters as the original
        # ones can be anywhere. Simply adopt second one.
        gmm.mean[altered[0],:] = gmm.mean[altered[1],:]
        gmm.covar[altered[0],:,:] = gmm.covar[altered[1],:,:]
        U[altered[0]] = U[altered[1]]

    # split 2, store in 1 and 2
    # following SVD method in Zhang 2003, with alpha=1/2, u = 1/4
    gmm.amp[altered[1]] = gmm.amp[altered[2]] = gmm.amp[altered[2]] / 2
    # TODO: replace with linalg.eigvalsh, but eigenvalues are not always ordered
    _, radius2, rotation = np.linalg.svd(gmm.covar[altered[2]])
    dl = np.sqrt(radius2[0]) *  rotation[0] / 4
    gmm.mean[altered[1]] = gmm.mean[altered[2]] - dl
    gmm.mean[altered[2]] = gmm.mean[altered[2]] + dl
    gmm.covar[altered[1:]] = np.linalg.det(gmm.covar[altered[2]])**(1/gmm.D) * np.eye(gmm.D)
    U[altered[1]] = U[altered[2]].copy() # now 1 and 2 have same U


# L-fold cross-validation of the fit function.
# all parameters for fit must be supplied with kwargs.
# the rng seed will be fixed for the CV runs so that all random effects are the
# same for each run.
def cv_fit(gmm, data, L=10, **kwargs):
    N = len(data)
    lcv = np.empty(N)

    if VERBOSITY:
        print ("running %d-fold cross-validation ..." % L)

    # CV and stacking can't have probabilistic inits that depends on
    # data or subsets thereof
    init_callback = kwargs.get("init_callback", None)
    if init_callback is not None:
        raise RuntimeError("Cross-validation can only be used consistently with init_callback=None")

    # make sure we know what the RNG is,
    # fix state of RNG to make behavior of fit reproducable
    rng = kwargs.get("rng", np.random)
    rng_state = rng.get_state()

    # need to copy the gmm when init_cb is None
    # otherwise runs start from different init positions
    gmm0 = GMM(K=gmm.K, D=gmm.D)
    gmm0.amp[:,] = gmm.amp[:]
    gmm0.mean[:,:] = gmm.mean[:,:]
    gmm0.covar[:,:,:] = gmm.covar[:,:,:]

    # same for bg if present
    bg = kwargs.get("background", None)
    if bg is not None:
        bg_amp0 = bg.amp

    # to L-fold CV here, need to split covar too if set
    covar = kwargs.pop("covar", None)
    for i in xrange(L):
        rng.set_state(rng_state)
        mask = np.arange(N) % L == i
        if covar is None or covar.shape == (gmm.D, gmm.D):
            fit(gmm, data[~mask], covar=covar, **kwargs)
            lcv[mask] = gmm.logL(data[mask], covar=covar)
        else:
            fit(gmm, data[~mask], covar=covar[~mask], **kwargs)
            lcv[mask] = gmm.logL(data[mask], covar=covar[mask])

        # undo for consistency
        gmm.amp[:,] = gmm0.amp[:]
        gmm.mean[:,:] = gmm0.mean[:,:]
        gmm.covar[:,:,:] = gmm0.covar[:,:,:]
        if bg is not None:
            bg.amp = bg_amp0

    return lcv


def stack(gmms, weights):
    # build stacked model by combining all gmms and applying weights to amps
    stacked = GMM(K=0, D=gmms[0].D)
    for m in xrange(len(gmms)):
        stacked.amp = np.concatenate((stacked.amp[:], weights[m]*gmms[m].amp[:]))
        stacked.mean = np.concatenate((stacked.mean[:,:], gmms[m].mean[:,:]))
        stacked.covar = np.concatenate((stacked.covar[:,:,:], gmms[m].covar[:,:,:]))
    stacked.amp /= stacked.amp.sum()
    return stacked


def stack_fit(gmms, data, kwargs, L=10, tol=1e-5, rng=np.random):
    M = len(gmms)
    N = len(data)
    lcvs = np.empty((M,N))

    for m in xrange(M):
        # run CV to get cross-validation likelihood
        rng_state = rng.get_state()
        lcvs[m,:] = cv_fit(gmms[m], data, L=L, **(kwargs[m]))
        rng.set_state(rng_state)
        # run normal fit on all data
        fit(gmms[m], data, **(kwargs[m]))

    # determine the weights that maximize the stacked estimator likelihood
    # run a tiny EM on lcvs to get them
    beta = np.ones(M)/M
    log_p_k = np.empty_like(lcvs)
    log_S = np.empty(N)
    it = 0
    if VERBOSITY:
        print ("optimizing stacking weights\n")
        print ("ITER\tLOG_L")
    while True and it < 20:
        log_p_k[:,:] = lcvs + np.log(beta)[:,None]
        log_S[:] = logsum(log_p_k)
        log_p_k[:,:] -= log_S
        beta[:] = np.exp(logsum(log_p_k, axis=1)) / N
        logL_ = log_S.mean()
        if VERBOSITY:
            print ("STACK%d\t%.4f" % (it, logL_))

        if it > 0 and logL_ - logL < tol:
            break
        logL = logL_
        it += 1
    if VERBOSITY:
        print ("")
    return stack(gmms, beta)
