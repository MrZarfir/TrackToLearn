import numpy as np

from typing import Tuple

from dipy.io.stateful_tractogram import Space, StatefulTractogram
from nibabel.streamlines import Tractogram

from TrackToLearn.algorithms.shared.offpolicy import ActorCritic
from TrackToLearn.datasets.utils import MRIDataVolume
from TrackToLearn.environments.env import BaseEnv
from TrackToLearn.environments.rollout_env import RolloutEnvironment
from TrackToLearn.environments.stopping_criteria import (
    is_flag_set, StoppingFlags)

import time


class TrackingEnvironment(BaseEnv):
    """ Tracking environment. This environment is used to track
    streamlines using a given model. Like the `BaseEnv`, it is
    used as both an environment and a "tracker".

    TODO: Clean up "_private functions" and public functions. Some could
    go into BaseEnv.
    """


    def _is_stopping(
        self,
        streamlines: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """ Check which streamlines should stop or not according to the
        predefined stopping criteria

        Parameters
        ----------
        streamlines : `numpy.ndarray` of shape (n_streamlines, n_points, 3)
            Streamlines that will be checked

        Returns
        -------
        stopping: `numpy.ndarray`
            Mask of stopping streamlines.
        stopping_flags : `numpy.ndarray`
            `StoppingFlags` that triggered stopping for each stopping
            streamline.
        """
        stopping, flags = \
            self._compute_stopping_flags(
                streamlines, self.stopping_criteria)
        return stopping, flags


    def nreset(self, n_seeds: int) -> np.ndarray:
        """ Initialize tracking seeds and streamlines. Will
        chose N random seeds among all seeds.

        TODO: Uniformize with `reset` function.

        Parameters
        ----------
        n_seeds: int
            How many seeds to sample

        Returns
        -------
        state: numpy.ndarray
            Initial state for RL model
        """

        super().reset()

        # Heuristic to avoid duplicating seeds if fewer seeds than actors.
        replace = n_seeds > len(self.seeds)
        seeds = np.random.choice(
            np.arange(len(self.seeds)), size=n_seeds, replace=replace)
        self.initial_points = self.seeds[seeds]

        self.streamlines = np.zeros(
            (n_seeds, self.max_nb_steps + 1, 3), dtype=np.float32)
        self.streamlines[:, 0, :] = self.initial_points

        self.flags = np.zeros(n_seeds, dtype=int)

        self.lengths = np.ones(n_seeds, dtype=np.int32)

        self.length = 1

        # Initialize rewards and done flags
        self.dones = np.full(n_seeds, False)
        self.continue_idx = np.arange(n_seeds)
        self.state = self._format_state(
            self.streamlines[self.continue_idx, :self.length])

        # Setup input signal
        return self.state[self.continue_idx]

    def reset(self, start: int, end: int) -> np.ndarray:
        """ Initialize tracking seeds and streamlines. Will select
        a given batch of seeds.

        TODO: Uniformize with `nreset` function.

        Parameters
        ----------
        start: int
            Starting index of seed to add to batch
        end: int
            Ending index of seeds to add to batch

        Returns
        -------
        state: numpy.ndarray
            Initial state for RL model
        """

        super().reset()

        # Initialize seeds as streamlines
        self.initial_points = self.seeds[start:end]
        N = self.initial_points.shape[0]

        self.streamlines = np.zeros(
            (N, self.max_nb_steps + 1, 3),
            dtype=np.float32)
        self.streamlines[:, 0, :] = self.initial_points
        self.flags = np.zeros(N, dtype=int)

        self.lengths = np.ones(N, dtype=np.int32)
        self.length = 1

        # Initialize rewards and done flags
        self.dones = np.full(N, False)
        self.continue_idx = np.arange(N)

        self.state = self._format_state(
            self.streamlines[self.continue_idx, :self.length])

        # Setup input signal
        return self.state[self.continue_idx]

    def step(
        self,
        actions: np.ndarray,
    ) -> Tuple[np.ndarray, list, bool, dict]:
        """
        Apply actions, rescale actions to step size and grow streamlines
        for one step forward. Calculate rewards and stop streamlines.

        Parameters
        ----------
        actions: np.ndarray
            Actions applied to the state

        Returns
        -------
        state: np.ndarray
            New state
        reward: list
            Reward for the last step of the streamline
        done: bool
            Whether the episode is done
        info: dict
        """

        directions = self._format_actions(actions)

        # Grow streamlines one step forward
        self.streamlines[self.continue_idx, self.length, :] = \
            self.streamlines[self.continue_idx, self.length-1, :] + directions
        self.length += 1

        # Get stopping and keeping indexes.
        stopping, new_flags = \
            self._is_stopping(
                self.streamlines[self.continue_idx, :self.length])

        # See which trajectory is stopping or continuing.
        # TODO: `investigate the use of `not_stopping`.
        self.not_stopping = np.logical_not(stopping)
        self.new_continue_idx, self.stopping_idx = \
            (self.continue_idx[~stopping],
             self.continue_idx[stopping])

        # Before declaring the trajectory over, we will backtrack a few steps on each failed trajectory and rollout a few times
        # for each failed trajectory and take the new trajectory that maximises a certain parameter (Oracle's value, or distance
        # to the border for example).
        before_rollout_stopping_idx = self.stopping_idx.copy()
        if self.do_rollout \
            and self.rollout_env.is_rollout_agent_set() \
            and (self.stopping_idx.size > 0) \
            and (self.length % self.roll_n_steps == 0):
            rollout_start_time = time.time()
            new_streamlines, new_continuing_streamlines, stopping_idx, stopping_flags = self.rollout_env.rollout(
                                    self.streamlines,
                                    self.stopping_idx,
                                    new_flags[stopping],
                                    self.length,
                                    self.stopping_criteria,
                                    self._format_state,
                                    self._format_actions,
                                    prob=0.1)

            rollout_end_time = time.time()
            print(f"Rollout time: {rollout_end_time - rollout_start_time}")

            self.streamlines = new_streamlines
            self.new_continue_idx = np.concatenate((self.new_continue_idx, new_continuing_streamlines))
            self.stopping_idx = stopping_idx  # TODO: Make sure this is correct
            new_flags[stopping] = stopping_flags  # TODO: Make sure this is correct

        # Keep the reason why tracking stopped
        self.flags[
            before_rollout_stopping_idx] = new_flags[stopping]

        # Keep which trajectory is over
        self.dones[self.stopping_idx] = 1

        reward = np.zeros(self.streamlines.shape[0])
        reward_info = {}
        # Compute reward if wanted. At valid time, no need
        # to compute it and slow down the tracking process
        if self.compute_reward:
            reward, reward_info = self.reward_function(
                self.streamlines[self.continue_idx, :self.length],
                self.dones[self.continue_idx])

        # Compute the state
        self.state[self.continue_idx] = self._format_state(
            self.streamlines[self.continue_idx, :self.length])

        return (
            self.state[self.continue_idx],
            reward, self.dones[self.continue_idx],
            {'continue_idx': self.continue_idx,
             'reward_info': reward_info})

    def harvest(
        self,
    ) -> Tuple[StatefulTractogram, np.ndarray]:
        """Internally keep track of which trajectories are still going
        and which aren't. Return the states accordingly.

        Returns
        -------
        states: np.ndarray of size [n_streamlines, input_size]
            States corresponding to continuing streamlines.
        continue_idx: np.ndarray
            Indexes of trajectories that did not stop.
        """

        # Register the length of the streamlines that have stopped.
        self.lengths[self.stopping_idx] = self.length
        # Set new "continue idx" based on the old idxes. This is to keep
        # the idxes "global".
        self.continue_idx = self.new_continue_idx
        # Return the state corresponding to streamlines that are actually
        # still being tracked.
        # TODO: investigate why `not_stopping` is returned.
        return self.state[self.continue_idx], self.not_stopping

    def get_streamlines(
        self,
        space=Space.RASMM,
        filter_streamlines=False
    ) -> StatefulTractogram:
        """ Obtain tracked streamlines from the environment.
        The last point will be removed if it raised a curvature or mask
        stopping criterion.

        Parameters
        ----------
        space: Space
            Space in which to return the streamlines. Default is RASMM.
        filter_streamlines: bool
            Whether to filter the streamlines using the filters defined
            in the environment.

        Returns
        -------
        tractogram: Tractogram
            Tracked streamlines in RASMM space.

        """
        # Harvest stopped streamlines and associated data
        # stopped_seeds = self.first_points[self.stopping_idx]
        stopped_streamlines = [self.streamlines[i, :self.lengths[i], :]
                               for i in range(len(self.streamlines))]

        # If the last point triggered a stopping criterion based on
        # angle, remove it so as not to produce ugly kinked streamlines.
        curvature_flags = is_flag_set(
            self.flags, StoppingFlags.STOPPING_CURVATURE)

        # Reduce overreach by removing the last point if it triggered
        # a mask-based stopping criterion.
        mask_flags = is_flag_set(
            self.flags, StoppingFlags.STOPPING_MASK)

        # Remove the last point if it triggered one of these two flags.
        flags = np.logical_or(curvature_flags, mask_flags)

        # IMPORTANT: The oracle will wildly
        # overestimate the tractogram if the last point is not included
        # since the last point (and segment) is what made it stop tracking.
        # **Therefore** the last point should be included as much as possible.
        stopped_streamlines = [
            s[:-1] if f else s for s, f in zip(stopped_streamlines, flags)]

        stopped_seeds = self.initial_points

        # Harvested tractogram
        tractogram = Tractogram(
            streamlines=stopped_streamlines,
            data_per_streamline={"seeds": stopped_seeds,
                                 "flags": self.flags,
                                 },
            affine_to_rasmm=self.affine_vox2rasmm)

        if filter_streamlines:
            for f, tract_filter in self.filters.items():
                tractogram = tract_filter(tractogram)

        if space == Space.RASMM:
            tractogram.apply_affine(self.affine_vox2rasmm)

        return tractogram
