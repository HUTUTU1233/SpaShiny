import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import numpy as np
import pandas as pd
from tqdm import tqdm
from captum.attr import IntegratedGradients, DeepLiftShap, GradientShap
from .model import SimpleNN


class River:
    # =========================
    # : device=None
    # =========================
    def __init__(self, gene_expression, spatial, label, device=None):   # <<<
        self.gene_expression = gene_expression
        self.spatial = spatial
        self.label = label

        # =========================
        # : 'cuda'
        # =========================
        if device is None:   # <<<
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        self.model = SimpleNN(
            gene_expression.shape[1],
            spatial.shape[1],
            np.unique(label).shape[0]
        ).to(self.device)

        self.final_rank = None

        # =========================
        # :label  long
        # =========================
        self.dataset = TensorDataset(
            torch.from_numpy(gene_expression).float(),
            torch.from_numpy(spatial).float(),
            torch.from_numpy(label).long()   # <<<
        )

        self.train_loader = DataLoader(self.dataset, batch_size=4096, shuffle=True)
        self.test_loader = DataLoader(self.dataset, batch_size=4096, shuffle=False)

        self.optimizer = optim.Adam(self.model.parameters(), lr=1e-3, weight_decay=1e-4)
        self.loss = nn.CrossEntropyLoss()
        self.n_features = gene_expression.shape[1]
        self.scores_ig = None
        self.scores_dl = None
        self.scores_sl = None

    def train(self, epoch=200):
        self.model.train()
        for ep in range(epoch):   # <<< : epoch
            for data, pos, targets in self.train_loader:
                data = data.to(self.device)
                pos = pos.to(self.device)
                targets = targets.to(self.device)

                outputs = self.model(data, pos)
                loss = self.loss(outputs, targets)

                self.optimizer.zero_grad(set_to_none=True)
                loss.backward()
                self.optimizer.step()

            print(f"Epoch [{ep+1}/{epoch}], Loss: {loss.item():.4f}")   # <<< : /100

            self.model.eval()
            with torch.no_grad():
                correct = 0
                total = 0
                for data, pos, targets in self.test_loader:
                    data = data.to(self.device)
                    pos = pos.to(self.device)
                    targets = targets.to(self.device)

                    outputs = self.model(data, pos)
                    _, predicted = torch.max(outputs.data, 1)
                    total += targets.size(0)
                    correct += (predicted == targets).sum().item()

            print("Accuracy of the network on the test data: %d %%" % (100 * correct / total))
            self.model.train()

    def attribution(self):
        # CPU , cuda
        try:
            torch.set_num_threads(max(1, min(4, torch.get_num_threads())))
        except Exception:
            pass

        ig = IntegratedGradients(self.model)
        dl = DeepLiftShap(self.model)
        sl = GradientShap(self.model)

        ig_attributions = []
        dl_attributions = []
        sl_attributions = []

        test_loader = DataLoader(self.dataset, batch_size=32, shuffle=False, drop_last=True)

        self.model.eval()

        # =========================
        # : cuda:3
        # =========================
        self.model.to(self.device)   # <<<

        for data, position, label in tqdm(test_loader):
            data = data.to(self.device)           # <<<
            position = position.to(self.device)   # <<<
            label = label.to(self.device)         # <<<

            baseline_gene = torch.zeros(data.shape[0], self.n_features, device=self.device)  # <<<

            ig_attribution = ig.attribute(
                (data, position),
                baselines=(baseline_gene, position),
                target=label
            )
            ig_attributions.append(abs(ig_attribution[0].cpu().detach()))
            del ig_attribution

            dl_attribution = dl.attribute(
                (data, position),
                baselines=(baseline_gene, position),
                target=label
            )
            dl_attributions.append(abs(dl_attribution[0].cpu().detach()))
            del dl_attribution

            sl_attribution = sl.attribute(
                (data, position),
                baselines=(baseline_gene, position),
                target=label
            )
            sl_attributions.append(abs(sl_attribution[0].cpu().detach()))
            del sl_attribution

            # =========================
            # : CUDA
            # =========================
            if "cuda" in str(self.device) and torch.cuda.is_available():   # <<<
                torch.cuda.empty_cache()

        return ig_attributions, dl_attributions, sl_attributions

    def summary_attribution(self, ig_attributions, dl_attributions, sl_attributions, overlap):
        final_score_ig = torch.cat(ig_attributions).reshape(-1, self.n_features)
        final_score_dl = torch.cat(dl_attributions).reshape(-1, self.n_features)
        final_score_sl = torch.cat(sl_attributions).reshape(-1, self.n_features)

        scores_ig = torch.nn.functional.normalize(final_score_ig, dim=1).detach()
        scores_dl = torch.nn.functional.normalize(final_score_dl, dim=1).detach()
        scores_sl = torch.nn.functional.normalize(final_score_sl, dim=1).detach()

        ig_rank_indices = torch.argsort(-scores_ig.sum(0))
        dl_rank_indices = torch.argsort(-scores_dl.sum(0))
        sl_rank_indices = torch.argsort(-scores_sl.sum(0))

        print(np.array(overlap)[ig_rank_indices][:10].tolist())
        print(np.array(overlap)[dl_rank_indices][:10].tolist())
        print(np.array(overlap)[sl_rank_indices][:10].tolist())

        ig_rank = torch.argsort(ig_rank_indices)
        dl_rank = torch.argsort(dl_rank_indices)
        sl_rank = torch.argsort(sl_rank_indices)

        data = {
            'Rank1': ig_rank.tolist(),
            'Rank2': sl_rank.tolist(),
            'Rank3': dl_rank.tolist()
        }
        df = pd.DataFrame(data)
        df.index = overlap

        n = len(df)
        borda_scores = df.apply(lambda x: n - x).sum(axis=1)
        final_ranks = borda_scores.sort_values(ascending=False)

        self.final_rank = final_ranks
        self.scores_ig = scores_ig
        self.scores_dl = scores_dl
        self.scores_sl = scores_sl

    def return_top_k_gene(self, top_k=200):
        return self.final_rank[:top_k].index.values   # <<< : 200

    def save_model(self, path):
        # =========================
        # :torch.save
        # =========================
        torch.save({"state_dict": self.model.state_dict()}, path)   # <<<

    def load_model(self, path):
        ckpt = torch.load(path, map_location=self.device)   # <<<
        self.model.load_state_dict(ckpt["state_dict"])
        self.model.to(self.device)
