from pathlib import Path

import transformers
import wandb
from peft import PromptTuningConfig, PromptTuningInit, TaskType, get_peft_model
from transformers import (
    AutoTokenizer,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainingArguments,
)

from chemnlp.data.utils import get_datasets, sample_dataset
from chemnlp.data_val.config import TrainPipelineConfig
from chemnlp.utils import load_config

HERE = Path(__file__).resolve()
CONFIG_PATH = HERE.parent.parent / "configs/accelerate_tune.yaml"


def run():
    raw_config = load_config(CONFIG_PATH)
    config = TrainPipelineConfig(**raw_config)
    print(config)

    model_ref = getattr(transformers, config.model.base)
    model = model_ref.from_pretrained(
        pretrained_model_name_or_path=config.model.name,
        revision=config.model.revision,
    )

    tokenizer = AutoTokenizer.from_pretrained(
        pretrained_model_name_or_path=config.model.name,
        revision=config.model.revision,
    )
    tokenizer.add_special_tokens({"pad_token": "<|padding|>"})

    peft_config = PromptTuningConfig(
        task_type=TaskType.CAUSAL_LM,
        prompt_tuning_init=PromptTuningInit.TEXT,
        num_virtual_tokens=config.prompt.num_virtual_tokens,
        prompt_tuning_init_text=config.prompt.prompt_tuning_init_text,
        tokenizer_name_or_path=config.model.name,
    )

    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()

    train_dataset, val_dataset = get_datasets(config, tokenizer)
    if config.data.subsample:
        train_dataset = sample_dataset(train_dataset, config.data.num_train_samples)
        val_dataset = sample_dataset(val_dataset, config.data.num_val_samples)

    data_collator = DataCollatorForLanguageModeling(
        tokenizer, mlm=False, pad_to_multiple_of=config.data.pad_to_multiple_of
    )

    training_args = TrainingArguments(
        output_dir=config.train.output_dir,
        evaluation_strategy="epoch",
        learning_rate=config.train.learning_rate,
        num_train_epochs=config.train.epochs,
        per_device_train_batch_size=config.train.per_device_train_batch_size,
        per_device_eval_batch_size=config.train.per_device_eval_batch_size,
        report_to="wandb" if config.train.is_wandb else None,
    )

    if config.train.is_wandb:
        wandb.init(
            project=config.train.wandb_project,
            name=f"{config.model.name}-{config.train.run_name}-finetuned",
            config=config.dict(),
        )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        tokenizer=tokenizer,
        data_collator=data_collator,
    )
    trainer.train()
    print(trainer.state.log_history)


if __name__ == "__main__":
    run()
