from comet_ml import Experiment as CometExperiment
import argparse
from TrackToLearn.trainers.sac_auto_train import SACAutoTrackToLearnTraining
from TrackToLearn.trainers.train import add_training_args
from TrackToLearn.algorithms.rl import RLAlgorithm
from TrackToLearn.environments.env import BaseEnv
from TrackToLearn.tracking.tracker import Tracker
from TrackToLearn.experiment.tractometer_validator import TractometerValidator
from TrackToLearn.experiment.oracle_validator import OracleValidator
import numpy as np
from TrackToLearn.algorithms.shared.utils import mean_losses, mean_rewards
from nibabel.streamlines import TrkFile
import torch
import tempfile
import os
from dipy.io.streamline import load_tractogram
from TrackToLearn.filterers.tractometer_filterer import TractometerFilterer
from dipy.io.stateful_tractogram import StatefulTractogram
from typing import Union


class RlhfTrackToLearnTraining(SACAutoTrackToLearnTraining):
    def __init__(
        self,
        rlhf_train_dto: dict,
        comet_experiment: CometExperiment,
        ):
        super().__init__(
            rlhf_train_dto,
            comet_experiment,
        )

        self.filterers = [TractometerFilterer()]


    def generate_and_save_tractogram(self, tracker: Tracker, env: BaseEnv, save_dir: str):
        tractogram = tracker.track(self.tracker_env, TrkFile)

        filename = self.save_rasmm_tractogram(
            tractogram, env.subject_id,
            env.affine_vox2rasmm, env.reference,
            save_dir
        )

        return filename

    def filter_tractogram(self, tractogram_file: str, env: BaseEnv, out_dir: str, base_dir: Union[tempfile.TemporaryDirectory, str]):
        """ Filter the tractogram (0 for invalid, 1 for valid) using the filterers

        TODO: Implement for more than one filterer
        """

        tractograms = [tractogram_file]
        filterer = self.filterers[0] # TODO: Implement for more than one filterer
        gt_config = env.gt_config
        filtered_tractogram = filterer(env.reference, tractograms, gt_config, out_dir, scored_extension="trk", tmp_base_dir=base_dir)
        return tractogram

    def select_streamline_pairs(self):
        pass

    def rlhf_loss(self):
        pass

    def train_reward(self):
        pass

    def train_rl_agent(self, alg: RLAlgorithm, env: BaseEnv, valid_env: BaseEnv):
        super().rl_train(alg, env, valid_env) # Train the agent

    def rl_train(
        self,
        alg: RLAlgorithm,
        env: BaseEnv,
        valid_env: BaseEnv
    ):
        """ Train the RL algorithm for N epochs. An epoch here corresponds to
        running tracking on the training set until all streamlines are done.
        This loop should be algorithm-agnostic. Between epochs, report stats
        so they can be monitored during training

        Parameters:
        -----------
            alg: RLAlgorithm
                The RL algorithm, either TD3, PPO or any others
            env: BaseEnv
                The tracking environment
            valid_env: BaseEnv
                The validation tracking environment (forward).
            """

        # Start by pretraining the RL agent to get reasonable results.
        self.train_rl_agent(alg, env, valid_env)

        self.tracker_env = self.get_valid_env()
        self.tracker = Tracker(
            alg, self.n_actor, prob=1.0, compress=0.0)

        # Setup filterers which will be used to filter tractograms
        # for the RLHF pipeline.  
        # self.filterers.append(TractometerValidator(
        #     self.scoring_data, self.tractometer_reference,
        #     dilate_endpoints=self.tractometer_dilate))

        # RLHF loop to fine-tune the oracle to the RL agent and vice-versa.
        num_iters = 5
        for i in range(num_iters):

            with tempfile.TemporaryDirectory() as tmpdir:
                # Generate a tractogram
                tractogram = self.generate_and_save_tractogram(tracker, self.tracker_env, tmpdir)

                # Filter the tractogram
                scored_tractogram = self.filter_tractogram(tractogram, tmpdir) # Need to filter for each filterer and keep the same order.

                # Select streamline pairs that originate from the same seed
                # We have the streamlines themselves and the scores for each filterer
                streamline_pairs = self.select_streamline_pairs()

                # Preference distrubution based on filtering scores
                # mu(1) = smax(nombre de fois la streamline 1 classée valide)
                # mu(2) = smax(nombre de fois la streamline 2 classée valide)
                # TODO

                # Run the reward network on those streamline pairs
                # TODO
                rewards = (5, -2)

                # Preference distribution Softmax on last axis for rewards
                # TODO

                # Compute loss
                loss = self.rlhf_loss()

                self.optimizer.zero_grad()
                loss.backward()
                self.optimizer.step()

                # Train reward model
                self.train_reward()

            # Train the RL agent
            self.train_rl_agent(alg, env, valid_env)


    def run(self):
        """ Prepare the environment, algorithm and trackers and run the
        training loop
        """
        super(RlhfTrackToLearnTraining, self).run()

def add_rlhf_training_args(parser):
    return parser    

def parse_args():
    """ Train a RL tracking agent using RLHF with PPO. """
    parser = argparse.ArgumentParser(
        description=parse_args.__doc__,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    add_training_args(parser)

    arguments = parser.parse_args()
    return arguments

def main():
    args = parse_args()
    
    # Create a Comet experiment
    experiment = CometExperiment(
        project_name=args.experiment,
        workspace=args.workspace, parse_args=False,
        auto_metric_logging=False,
        disabled=not args.use_comet
    )

    # Create and run the experiment
    rlhf_experiment = RlhfTrackToLearnTraining(
        vars(args),
        experiment
    )
    rlhf_experiment.run()


if __name__ == "__main__":
    main()