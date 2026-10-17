# Sensor signal classification results

1,600 synthetic records from 40 simulated devices; split sizes: {'train': 960, 'validation': 320, 'test': 320}.
Selected model: **Logistic regression**, chosen using validation macro F1 before test evaluation.

| Model | Validation macro F1 | Test accuracy | Test macro F1 |
| --- | ---: | ---: | ---: |
| Dummy | 10.00% | 25.00% | 10.00% |
| EE rules | 89.19% | 86.25% | 85.87% |
| Logistic regression | 100.00% | 99.69% | 99.69% |
| Random forest | 100.00% | 100.00% | 100.00% |

The test contains separate device IDs, with the same synthetic generation rules and nominal noise range as training.
The noise sweep reuses those held-out devices with paired records at fixed SNR levels. These are dependent stress conditions, not additional independent test subjects.
No real sensor data, real fault diagnosis, calibrated probabilities, or deployment performance is claimed.
The four generated conditions are intentionally isolated. Mixed faults and unseen fault types are outside the label set.
