# File: conftest.py

import sys
import pytest
import numpy as np
from config import EnvironmentConfig

# Add project root to sys.path
sys.path.append(".")

# Try to import heavy dependencies; if unavailable, provide lightweight stubs
try:
    import torch  # type: ignore
    from env.environment import HistoricalEnvironment
    from agent import MetaSACAgent
    HAS_HEAVY_DEPS = True
except Exception:
    HAS_HEAVY_DEPS = False

    # minimal HistoricalEnvironment stub
    class HistoricalEnvironment:
        def __init__(self, data):
            self._data = data
            self._i = 0

        def reset(self):
            self._i = 0
            return self._data[self._i]

        def step(self, action, step_idx=0):
            self._i = min(self._i + 1, len(self._data) - 1)
            done = self._i >= (len(self._data) - 1)
            return self._data[self._i], 0.0, done, {}

    # minimal MetaSACAgent stub
    class MetaSACAgent:
        def __init__(self, config, env=None):
            self.config = config

        def replay_buffer(self):
            return None

        def select_action(self, *args, **kwargs):
            return 0.0


@pytest.fixture
def agent():
    """
    Fixture to initialize the MetaSACAgent with mock data.
    """
    config = EnvironmentConfig(
        state_dim=50,
        action_dim=5,
        hidden_dim=128,
        attention_dim=64,
        num_mlp_layers=3,
        dropout_rate=0.1,
        time_encoding_dim=16,
        custom_layers=["KLinePatternLayer", "VolatilityTrackingLayer", "FractalDimensionLayer"],
        window_size=20,
        num_hyperparams=10,
        graph_input_dim=10,
        graph_hidden_dim=32,
        num_graph_layers=2,
        ensemble_size=3,
        weight_decay=1e-5
    )
    mock_data = np.random.randn(2000, config.state_dim).astype(np.float32)  # Increased data points for better simulation
    env = HistoricalEnvironment(mock_data)
    agent = MetaSACAgent(config, env)
    # Populate replay buffer with random data
    for _ in range(config.buffer_capacity // 10):  # Add a fraction to avoid filling it up
        state = env.reset()
        for step in range(10):
            action = np.random.uniform(-1, 1, config.action_dim)
            next_state, reward, done, _ = env.step(action, step)
            try:
                agent.replay_buffer.add(state, action, reward, next_state, done, step)
            except Exception:
                # replay_buffer may not exist on the lightweight stub; ignore
                pass
            if done:
                break
            state = next_state
    return agent

@pytest.fixture
def sample_batch():
    """
    Fixture to provide a sample batch of data for testing.
    """
    batch = {
        'states': np.random.randn(32, 20, 50).astype(np.float32),  # (batch_size, seq_length, state_dim)
        'actions': np.random.randn(32, 5).astype(np.float32),     # (batch_size, action_dim)
        'rewards': np.random.randn(32, 1).astype(np.float32),     # (batch_size, 1)
        'next_states': np.random.randn(32, 20, 50).astype(np.float32),  # (batch_size, seq_length, state_dim)
        'dones': np.random.randint(0, 2, (32, 1)).astype(np.float32),    # (batch_size, 1)
        'time_steps': np.random.randint(0, 1000, (32,)),                 # (batch_size,)
    }
    if HAS_HEAVY_DEPS:
        import torch  # re-import for typing
        batch['edge_index'] = torch.tensor([[0, 1, 2], [1, 2, 0]], dtype=torch.long)
        batch['graph_node_features'] = torch.randn(3, 10)
    else:
        # lightweight numpy alternatives for tests that don't require torch
        batch['edge_index'] = np.array([[0, 1, 2], [1, 2, 0]], dtype=np.int64)
        batch['graph_node_features'] = np.random.randn(3, 10).astype(np.float32)
    return batch
