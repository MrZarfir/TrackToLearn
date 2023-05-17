#!/bin/bash

set -e  # exit if any command fails

DATASET_FOLDER=${TRACK_TO_LEARN_DATA}/
WORK_DATASET_FOLDER=${LOCAL_TRACK_TO_LEARN_DATA}/

VALIDATION_SUBJECT_ID=ismrm2015
SUBJECT_ID=ismrm2015
EXPERIMENTS_FOLDER=${DATASET_FOLDER}/experiments
WORK_EXPERIMENTS_FOLDER=${WORK_DATASET_FOLDER}/experiments
SCORING_DATA=${DATASET_FOLDER}/datasets/${VALIDATION_SUBJECT_ID}/scoring_data

mkdir -p $WORK_DATASET_FOLDER/datasets/${SUBJECT_ID}

echo "Transfering data to working folder..."
cp -rnv "${DATASET_FOLDER}"/datasets/${VALIDATION_SUBJECT_ID} "${WORK_DATASET_FOLDER}"/datasets/
cp -rnv "${DATASET_FOLDER}"/datasets/${SUBJECT_ID} "${WORK_DATASET_FOLDER}"/datasets/

dataset_file=$WORK_DATASET_FOLDER/datasets/${SUBJECT_ID}/${SUBJECT_ID}.hdf5
validation_dataset_file=$WORK_DATASET_FOLDER/datasets/${VALIDATION_SUBJECT_ID}/${VALIDATION_SUBJECT_ID}.hdf5
reference_file=$WORK_DATASET_FOLDER/datasets/${VALIDATION_SUBJECT_ID}/masks/${VALIDATION_SUBJECT_ID}_wm.nii.gz

# RL params
max_ep=1000 # Chosen empirically
log_interval=50 # Log at n episodes
lr=0.00005 # Learning rate
gamma=0.5 # Gamma for reward discounting
action_std=0.0
eps_clip=0.1
lmbda=0.95
K_epochs=30
entropy_loss_coeff=0.001

# Model params
prob=0.0 # Noise to add to make a prob output. 0 for deterministic

# Env parameters
npv=20 # Seed per voxel
theta=30 # Maximum angle for streamline curvature

EXPERIMENT=PPO_ISMRM2015TrainExp2

ID=2023-03-06-12_22_46

seeds=(1111 2222 3333 4444 5555)
rng_seed=$1

# for rng_seed in "${seeds[@]}"
# do

DEST_FOLDER="$WORK_EXPERIMENTS_FOLDER"/"$EXPERIMENT"/"$ID"/"$rng_seed"

python TrackToLearn/trainers/ppo_train.py \
  $DEST_FOLDER \
  "$EXPERIMENT" \
  "$ID" \
  "${dataset_file}" \
  "${SUBJECT_ID}" \
  "${validation_dataset_file}" \
  "${VALIDATION_SUBJECT_ID}" \
  "${reference_file}" \
  "${SCORING_DATA}" \
  --max_ep=${max_ep} \
  --log_interval=${log_interval} \
  --lr=${lr} \
  --gamma=${gamma} \
  --action_std=${action_std} \
  --entropy_loss_coeff=${entropy_loss_coeff} \
  --eps_clip=${eps_clip} \
  --lmbda=${lmbda} \
  --K_epochs=${K_epochs} \
  --rng_seed=${rng_seed} \
  --npv=${npv} \
  --theta=${theta} \
  --interface_seeding \
  --use_comet \
  --use_gpu \
  --run_tractometer

mkdir -p $EXPERIMENTS_FOLDER/"$EXPERIMENT"
mkdir -p $EXPERIMENTS_FOLDER/"$EXPERIMENT"/"$ID"
mkdir -p $EXPERIMENTS_FOLDER/"$EXPERIMENT"/"$ID"/
cp -f -r $DEST_FOLDER "$EXPERIMENTS_FOLDER"/"$EXPERIMENT"/"$ID"/

# done