#!/usr/bin/env python
import comet_ml  # noqa: F401 ugh
import torch

from TrackToLearn.trainers.sac_auto_train import (
    parse_args,
    SACAutoTrackToLearnTraining)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
assert torch.cuda.is_available()


def main():
    """ Main tracking script """
    args = parse_args()
    print(args)
    from comet_ml import Optimizer

    # We only need to specify the algorithm and hyperparameters to use:
    config = {
        # We pick the Bayes algorithm:
        "algorithm": "grid",

        # Declare your hyperparameters in the Vizier-inspired format:
        "parameters": {
            "lr": {
                "type": "discrete",
                "values": [5e-4, 1e-3, 5e-3]},
            "gamma": {
                "type": "discrete",
                "values": [0.95, 0.99]},
            "alpha": {
                "type": "discrete",
                "values": [0.2]},
            "coverage_weighting": {
                "type": "discrete",
                "values": [0.0]},
            "oracle_weighting": {
                "type": "discrete",
                "values": [0.0, 1., 5., 10., 20.]},
        },

        # Declare what we will be optimizing, and how:
        "spec": {
            "metric": "VC",
            "objective": "maximize",
            "seed": args.rng_seed,
            "retryLimit": 3,
            "retryAssignLimit": 3,
        },
    }

    # Next, create an optimizer, passing in the config:
    opt = Optimizer(config)

    for experiment in opt.get_experiments(project_name=args.experiment):
        experiment.auto_metric_logging = False
        experiment.workspace = args.workspace
        experiment.parse_args = False
        experiment.disabled = not args.use_comet

        lr = experiment.get_parameter("lr")
        gamma = experiment.get_parameter("gamma")
        alpha = experiment.get_parameter("alpha")
        coverage_weighting = experiment.get_parameter("coverage_weighting")
        oracle_weighting = experiment.get_parameter("oracle_weighting")

        arguments = vars(args)
        arguments.update({
            'lr': lr,
            'gamma': gamma,
            'alpha': alpha,
            'coverage_weighting': coverage_weighting,
            'oracle_weighting': oracle_weighting,
        })

        sac_experiment = SACAutoTrackToLearnTraining(
            arguments,
            experiment
        )
        sac_experiment.run()


if __name__ == '__main__':
    main()