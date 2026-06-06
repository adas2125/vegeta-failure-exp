### Getting Load Generators to Fail

Experiments were reproduced on `clnode126` and `clnode112` in the Clemson cluster on CloudLab.
Raw results for the experiments can be found [here](https://drive.google.com/drive/u/0/folders/1a5cJLxxO9OH1CJLueoE2c6JwvLM4jZXt).
To reproduce the analysis of vegeta and k6 failures, please download the zip files `results.zip` and `phase-smooth-data.zip`, respectively.

Start by cloning this repository.

Then clone the Vegeta and k6 repositories so you can run the relevant
experiments.

```sh
git clone https://github.com/grafana/k6.git
```

```sh
git clone https://github.com/tsenart/vegeta.git
```

Once these repositories are available, copy the relevant scripts from this
repository into the corresponding experiment repositories.
