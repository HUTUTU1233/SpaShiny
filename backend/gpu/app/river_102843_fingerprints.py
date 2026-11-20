"""Public fingerprints only; no raw RNG state or model weights."""
REFERENCE={
    "file_order": [
        "eaf39cdc830be91cd9886e273e689b19afef9fd3176de6da0fb56ef157a7b49e",
        "175fe194e2afb0325ae5a2d06c0d0140dbad5d3b739032b4d89eb15ba327625f",
        "fe19ff80e7badc364e3516ac1f4b201efa594cf686d11ee774a216dc52d378a9",
        "78ae752b47414c3be277ac08f0f4e2cd35d0049fe364fe3f5a403bb73719b1c2",
        "b0e0754ac6267d8c412fb70616b16eef017e575b4b301ae8ca39a1563f887811"
    ],
    "source_spots": [
        3540,
        2579,
        2438,
        2363,
        1052
    ],
    "initial_model": {
        "exp_encoder.0.weight": {
            "shape": [
                64,
                32140
            ],
            "dtype": "float32",
            "sha256": "7de0ffdc80883f6fdb3f3387dc706ba6727c6b89330fb0fe5b287d7b75726b2a"
        },
        "exp_encoder.0.bias": {
            "shape": [
                64
            ],
            "dtype": "float32",
            "sha256": "349bf90d7b3767d13231d6feeec77230090eb6bc1b85baad0c2dcabf477a823f"
        },
        "exp_encoder.3.weight": {
            "shape": [
                64,
                64
            ],
            "dtype": "float32",
            "sha256": "9db1385e980839e96c9bf7784e1a3f3fc09ad889469a96980be7f70c845dd452"
        },
        "exp_encoder.3.bias": {
            "shape": [
                64
            ],
            "dtype": "float32",
            "sha256": "fb37a427eaed53823ee745ea91f3f1171d7d756a7d153bda064b328ae73ec39b"
        },
        "position_encoder.0.weight": {
            "shape": [
                64,
                2
            ],
            "dtype": "float32",
            "sha256": "97165745eca219a7a2082c1d6c369958d17fa441b029a262b159a0e392193f5a"
        },
        "position_encoder.0.bias": {
            "shape": [
                64
            ],
            "dtype": "float32",
            "sha256": "88e46621e0c1883657152a23d56cf89f35ea992ee61572e8a5cc43e30c647a18"
        },
        "position_encoder.3.weight": {
            "shape": [
                64,
                64
            ],
            "dtype": "float32",
            "sha256": "4001604409503a960b10762682a45c6f3f09a88b16bd67ccbe7ad7f54fba353d"
        },
        "position_encoder.3.bias": {
            "shape": [
                64
            ],
            "dtype": "float32",
            "sha256": "f967df1df99dd11609656d99613d14d460bf0b97fe5dbaad8d8ce66747d07cc5"
        },
        "classifier.0.weight": {
            "shape": [
                64,
                128
            ],
            "dtype": "float32",
            "sha256": "8b54d840584ba953e12d885e8c34608b12ed53f94d2d263a221ca33946ba30fc"
        },
        "classifier.0.bias": {
            "shape": [
                64
            ],
            "dtype": "float32",
            "sha256": "aca818828e98b7937f9953e70c911e661751e5b09a08a61852b86f6409da9928"
        },
        "classifier.3.weight": {
            "shape": [
                32,
                64
            ],
            "dtype": "float32",
            "sha256": "ed4bd6efcf21718d8d63a05850408a4b45f7c5185d5a33831863617cc3702df9"
        },
        "classifier.3.bias": {
            "shape": [
                32
            ],
            "dtype": "float32",
            "sha256": "a1e7bbbe02b84186a9590a02ed46e533ca8491ad3c6369165e021354b5b4d44b"
        },
        "classifier.6.weight": {
            "shape": [
                5,
                32
            ],
            "dtype": "float32",
            "sha256": "7bea2d0be5e87530a837ca5f53f8730e1ffbe78975beb26f26d378d0942f91d7"
        },
        "classifier.6.bias": {
            "shape": [
                5
            ],
            "dtype": "float32",
            "sha256": "d1c1f4a74b99be0809ae73d27793249c4ef17fa82a118a2eff3a3d3029ef4381"
        }
    },
    "cpu_rng": {
        "python_sha256": "21feb557e3da2a52be59d0a03105f7314322a903b4cca49a0e125c43cf2885d0",
        "numpy_sha256": "a8cfe8077a095f5c0b50117848a0462c59002af0131f2a160b5a538e96d55630",
        "torch_cpu_sha256": "00ba3e5f4f5ce218e11303bacf030a707fbf787529a615f2131ef6a706b61315"
    },
    "cuda0_rng": "23e4023b54348035999d662ccd6e8dfc517d956d7a34e2c274cad0d105717058"
}
